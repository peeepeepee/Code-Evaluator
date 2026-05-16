import json
import logging
from typing import Dict, List, Tuple, Any, Optional
from pydantic import BaseModel, Field

from app.agents.rubric_extractor_agent import RubricExtractorAgent
from app.agents.evaluation_guidance_agent import EvaluationGuidanceAgent
from app.agents.approach_explanation_agent import ApproachExplanationAgent, ApproachExplanation

from app.utils.rubric_parser import parse_rubric, get_total_marks, identify_best_approach
from app.utils.security import check_for_injection, detection_based_check, create_security_wrapper
from app.utils.sanitizer import process_inputs
from app.utils.llm_utils import query_llm
from app.db.models import ExampleSubmission
from app.services.llm_client_service import LLMClientService
from dotenv import load_dotenv
load_dotenv()
import os
SECURITY_CHECK_ENABLED = os.getenv("SECURITY_CHECK_ENABLED", "true").lower() == "true"
DETECTION_CHECKS_ENABLED = os.getenv("DETECTION_CHECKS_ENABLED", "true").lower() == "true"

logger = logging.getLogger(__name__)

# Models
class FeedbackItem(BaseModel):
    points_awarded: int = 0
    max_points: int = 0
    feedback: str = ""

class EvaluationResponse(BaseModel):
    score: int = 0
    max_score: int = 0
    feedback: Dict[str, FeedbackItem] = {}
    error: Optional[str] = None

class EvaluationRequest(BaseModel):
    problem_statement: str
    rubric: str
    student_code: str
    model_solution: Optional[List[str]] = None
    problem_id: Optional[int] = None  # To identify which problem's guidance to retrieve
    language: str = "java"
    db: Optional[Any] = None  # Database session for retrieving guidance

    class Config:
        arbitrary_types_allowed = True  # Allow SQLAlchemy Session object

class EvaluationService:
    """
    Service responsible for evaluating student code submissions against rubrics
    using multiple evaluation techniques and LLM-based analysis.
    """
    
    def __init__(self):
        self.rubric_extractor = RubricExtractorAgent()
        self.approach_explainer = ApproachExplanationAgent()
        self.guidance_agent = EvaluationGuidanceAgent()
        self.llm_client = LLMClientService()
        
    async def complete_rubric_evaluation(self, request: EvaluationRequest) -> Dict[str, Any]:
        """
        Implement Complete Rubric Evaluation (CRE) as described in the paper
        
        Args:
            request: Evaluation request containing problem, rubric, and code
            
        Returns:
            Evaluation results
        """
        # Process and sanitize inputs
        problem, rubric_text, code = process_inputs(
            request.problem_statement,
            request.rubric,
            request.student_code
        )
        
        # Parse the rubric
        parsed_rubric = parse_rubric(rubric_text)
        
        # Create a secure prompt for the LLM
        prompt = await self.llm_client.construct_evaluation_prompt(
            problem,
            rubric_text,
            code,
            model_solution=request.model_solution
        )
        
        # Secure the prompt
        secured_prompt = create_security_wrapper(prompt)
        
        # Query the LLM
        response_text = await query_llm(secured_prompt)
        
        # Parse the response
        evaluation = self.llm_client.parse_llm_response(response_text)
        
        return evaluation

    async def pointwise_rubric_evaluation(self, request: EvaluationRequest) -> Dict[str, Any]:
        """
        Implement Pointwise Rubric Evaluation (PRE) as described in the paper
        
        Args:
            request: Evaluation request containing problem, rubric, and code
            
        Returns:
            Evaluation results with per-point scores
        """
        # Process and sanitize inputs
        problem, rubric_text, code = process_inputs(
            request.problem_statement,
            request.rubric,
            request.student_code
        )
        
        # Parse the rubric
        parsed_rubric = parse_rubric(rubric_text)
        
        # Identify the best approach (or try all if needed)
        best_approach = identify_best_approach(parsed_rubric)
        approach_points = parsed_rubric["approaches"][best_approach]["points"]
        
        results = {
            "approach_used": best_approach,
            "evaluation": {},
            "total_score": 0,
            "max_possible_score": get_total_marks(parsed_rubric),
            "feedback": ""
        }
        
        # Evaluate each point individually
        for point in approach_points:
            point_id = point["id"]
            description = point["description"]
            max_marks = point["marks"]
            
            # Use the LLM client service to generate criterion evaluation
            point_evaluation = await self.llm_client.generate_criterion_evaluation(
                problem, 
                description, 
                max_marks, 
                code
            )
            
            # Add to results
            results["evaluation"][point_id] = point_evaluation
            results["total_score"] += point_evaluation.get("marks_awarded", 0)
        
        # Generate overall feedback
        results["feedback"] = await self.llm_client.generate_feedback_summary(
            problem,
            results["evaluation"],
            results["total_score"],
            results["max_possible_score"]
        )
        
        return results

    async def evaluate_submission(self, request: EvaluationRequest) -> EvaluationResponse:
        """
        Main function to evaluate a submission using the appropriate technique
        with enhanced algorithm-specific guidance from examples
        
        Args:
            request: Evaluation request with problem, rubric, and code
            
        Returns:
            Evaluation response with score and feedback
        """
        try:
            if request.model_solution is None:
                model_solutions = []
                
                # Check if we have database access and problem_id
                if request.db is not None and request.problem_id is not None:
                    # Query for correct example submissions for this problem
                    correct_examples = request.db.query(ExampleSubmission).filter(
                        ExampleSubmission.problem_id == request.problem_id,
                        ExampleSubmission.tag.ilike("Correct%")  # Case-insensitive search for tags starting with "correct"
                    ).all()
                    
                    # Extract the code from these examples
                    if correct_examples:
                        for example in correct_examples:
                            model_solutions.append(example.code)
                        
                        logger.info(f"Found {len(model_solutions)} model solutions from database for problem {request.problem_id}")
                    else:
                        logger.info(f"No model solutions found in database for problem {request.problem_id}")
                
                request.model_solution = model_solutions if model_solutions else None
            
            example_feedback = []
            if request.db is not None and request.problem_id is not None:
                try:
                    from app.db.models import ExampleFeedback
                    
                    # Query for example feedback for this problem
                    feedback_entries = request.db.query(ExampleFeedback).filter(
                        ExampleFeedback.problem_id == request.problem_id
                    ).all()
                    
                    # Format feedback as list of dictionaries
                    if feedback_entries:
                        for entry in feedback_entries:
                            example_feedback.append({
                                "tag": entry.tag,
                                "feedback": entry.feedback_text
                            })
                        
                        logger.info(f"Found {len(example_feedback)} example feedback entries for problem {request.problem_id}")
                    else:
                        logger.info(f"No example feedback found for problem {request.problem_id}")
                except Exception as e:
                    logger.error(f"Error fetching example feedback: {str(e)}")
            


            # Process inputs for better handling
            problem, rubric_text, code = process_inputs(
                request.problem_statement,
                request.rubric,
                request.student_code
            )
            
            # First, generate the approach explanation
            try:
                approach_explanation = await self.approach_explainer.explain_approach(
                    code,
                    problem  # Pass problem statement for context
                )
                
                logger.info(f"Generated approach explanation: {approach_explanation.approach_name}")
            except Exception as e:
                logger.error(f"Error getting approach explanation: {str(e)}")
                approach_explanation = None
            
            # Extract the appropriate rubric based on the solution
            extracted_rubric = await self.rubric_extractor.extract_rubric_for_solution(
                problem,
                rubric_text,
                code,
                request.model_solution,
                approach_explanation  # Pass the approach explanation
            )
            
            # Get the correctly formatted rubric for evaluation
            formatted_rubric = await self.rubric_extractor.format_rubric_for_evaluation(extracted_rubric)
            
            # Format the approach explanation for the evaluator
            formatted_approach_explanation = self.approach_explainer.format_approach_explanation(approach_explanation) if approach_explanation else ""
            
            # Log the extracted approach and max score
            logger.info(f"Using approach: {extracted_rubric.approach} with max score: {extracted_rubric.max_score}")
            
            # Store the rubric points for reference to get correct max_points later
            rubric_points = {}
            if extracted_rubric.is_custom:
                for i, point in enumerate(extracted_rubric.rubric["points"]):
                    rubric_points[str(i+1)] = point["marks"]
            else:
                for i, point in enumerate(extracted_rubric.rubric["points"]):
                    rubric_points[str(i+1)] = point["marks"]
            
            logger.info(f"Rubric points mapping: {rubric_points}")
            
            # Generate algorithm-specific guidance using the extracted approach
            algorithm_guidance = None
            if request.db is not None and request.problem_id is not None:
                # Get guidance from database
                algorithm_guidance = await self.guidance_agent.get_guidance_from_db(
                    request.db, 
                    request.problem_id
                )
                
                if algorithm_guidance:
                    logger.info(f"Retrieved algorithm guidance from database for problem {request.problem_id}")
                else:
                    logger.warning(f"No algorithm guidance found in database for problem {request.problem_id}")


            # Use the LLM client to construct an evaluation prompt
            
            evaluation_prompt = await self.llm_client.construct_evaluation_prompt(
                problem,
                formatted_rubric,
                code,
                model_solution=request.model_solution,
                algorithm_guidance=algorithm_guidance.dict() if algorithm_guidance else None,
                approach_explanation=formatted_approach_explanation,
                example_feedback=example_feedback  # Include example feedback
            )
            
            # Create a secure version of the prompt
            secured_evaluation_prompt = create_security_wrapper(evaluation_prompt)
            
            # Use the LLM client's evaluate_with_prompt method
            evaluation = await self.llm_client.evaluate_with_prompt(secured_evaluation_prompt)
            
            # Convert the evaluation to a structured response
            feedback_dict = {}
            total_score = 0
            
            for point_id, point_eval in evaluation.get("evaluation", {}).items():
                # Get max_points from the parsed rubric instead of the LLM evaluation
                max_points = rubric_points.get(point_id, 1)  # Default to 1 if not found
                
                # Ensure points_awarded never exceeds max_points
                points_awarded = min(point_eval.get("marks_awarded", 0), max_points)
                
                feedback_dict[point_id] = FeedbackItem(
                    points_awarded=points_awarded,
                    max_points=max_points,
                    feedback=point_eval.get("justification", "")
                )
                
                total_score += points_awarded
            
            # Create response object
            return EvaluationResponse(
                score=total_score,
                max_score=extracted_rubric.max_score,
                feedback=feedback_dict,
                error=None
            )
            
        except Exception as e:
            logger.error(f"Error evaluating submission: {str(e)}", exc_info=True)
            return EvaluationResponse(
                score=0,
                max_score=0,
                feedback={},
                error=f"An error occurred during evaluation: {str(e)}"
            )
            
    async def security_check(self, code: str) -> Dict[str, Any]:
        """
        Perform security checks on the submitted code
        
        Args:
            code: Student code to check
            
        Returns:
            Dictionary with security check results
        """
        # Static pattern matching
        if SECURITY_CHECK_ENABLED:
            has_injection, issues = check_for_injection(code)
            if has_injection:
                return {
                    "passed": False,
                    "issues": issues
                }
        
        # LLM-based detection check
        if DETECTION_CHECKS_ENABLED:
            detection_result = await detection_based_check(code)
            if not detection_result.is_secure:
                return {
                    "passed": False,
                    "issues": detection_result.issues_detected or ["Detection check failed"]
                }
        
        return {
            "passed": True,
            "issues": []
        }