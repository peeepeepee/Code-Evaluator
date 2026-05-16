import json
import logging
import re
import asyncio
from typing import Dict, List, Any, Tuple, Optional
from pydantic import BaseModel, Field

from app.agents.approach_explanation_agent import ApproachExplanationAgent, ApproachExplanation
from app.utils.rubric_parser import parse_rubric, get_approach_marks
from app.utils.llm_utils import query_llm
from app.utils.sanitizer import process_inputs, remove_java_comments

logger = logging.getLogger(__name__)
nl = "\n"

class ApproachEvaluation(BaseModel):
    """Schema for approach evaluation result"""
    approach: str
    confidence: float = 0.0
    explanation: str = ""
    key_indicators: List[str] = []

class ExtractedRubric(BaseModel):
    """Schema for extracted rubric information"""
    is_custom: bool = False
    approach: str
    rubric: Dict[str, Any]
    explanation: str
    original_rubric: Dict[str, Any]
    max_score: int
    all_evaluations: List[ApproachEvaluation]
    approach_explanation: Optional[ApproachExplanation] = None

class RubricExtractorAgent:
    """
    Agent responsible for extracting and selecting the most appropriate rubric approach
    based on student solution. Evaluates each approach in parallel without knowledge of other approaches.
    """
    
    
        
    
    async def extract_rubric_for_solution(
        self, 
        problem_statement: str, 
        rubric: str, 
        solution_code: str,
        model_solution: Optional[List[str]] = None,
        approach_explanation: Optional[ApproachExplanation] = None
    ) -> ExtractedRubric:
        """
        Extract relevant rubric information based on the provided solution.
        Evaluates each approach in parallel and selects the one with highest confidence,
        augmented by ApproachExplanationAgent insights.
        
        Args:
            problem_statement: The problem statement
            rubric: The evaluation rubric text
            solution_code: The student's solution code
            model_solution: Optional model solution provided by instructor
            approach_explanation: Optional pre-generated approach explanation
            
        Returns:
            ExtractedRubric containing the extracted rubric information
        """
        # Process and sanitize inputs
        solution_without_comments = remove_java_comments(solution_code)
        
        clean_problem, clean_rubric, clean_solution = process_inputs(
            problem_statement, rubric, solution_without_comments
        )
        
        # Parse the rubric structure
        parsed_rubric = parse_rubric(clean_rubric)
        
        # First, run the parallel approach evaluation
        approach_results = await self._evaluate_approaches_in_parallel(
            clean_problem, 
            parsed_rubric, 
            clean_solution,
            model_solution
        )
        
        # If approach explanation is not provided, generate it
        if approach_explanation is None:
            approach_explainer = ApproachExplanationAgent()
            try:
                approach_explanation = await approach_explainer.explain_approach(
                    solution_code, 
                    problem_statement
                )
                logger.info(f"Generated approach explanation: {approach_explanation.approach_name}")
            except Exception as e:
                logger.error(f"Error getting approach explanation: {str(e)}")
                approach_explanation = None
        
        # Augment approach results with explanation insights (if available)
        augmented_approach_results = []
        if approach_explanation:
            augmented_approach_results = self._augment_approach_results(
                approach_results, 
                approach_explanation, 
                parsed_rubric
            )
        else:
            augmented_approach_results = approach_results
        
        # Select best approach with augmented information
        best_approach = self._select_best_approach(
            augmented_approach_results, 
            parsed_rubric
        )
        
        # Get approach name and details
        approach_name = best_approach["approach"]
        confidence = best_approach["confidence"]
        explanation = best_approach["explanation"]
        
        logger.info(f"Selected best approach: {approach_name} with confidence {confidence}")
        approach_max_score = get_approach_marks(parsed_rubric, approach_name)
        logger.info(f"Approach {approach_name} has a maximum score of {approach_max_score}")
        
        # Convert approach evaluations to model instances
        approach_evaluation_models = [
            ApproachEvaluation(**eval_result) for eval_result in augmented_approach_results
        ]
        
        # Create and return the ExtractedRubric model
        return ExtractedRubric(
            is_custom=False,
            approach=approach_name,
            rubric=parsed_rubric["approaches"][approach_name],
            explanation=explanation,
            original_rubric=parsed_rubric,
            max_score=approach_max_score,
            all_evaluations=approach_evaluation_models,
            approach_explanation=approach_explanation
        )
    
    def _augment_approach_results(
        self,
        approach_results: List[Dict[str, Any]],
        approach_explanation: ApproachExplanation,
        parsed_rubric: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Augment approach results with insights from approach explanation,
        focusing on specificity to differentiate similar approaches.
        Structure remains compatible: returns List[Dict[str, Any]].

        Args:
            approach_results: Original approach evaluation results from LLM.
            approach_explanation: Explanation from ApproachExplanationAgent.
            parsed_rubric: Parsed rubric structure containing details for each approach.

        Returns:
            Augmented approach results (List of Dicts with 'approach', 'confidence', 'explanation', 'key_indicators').
        """
        

        if not approach_results:
            
            return [] # Return empty list, compatible type

        # Extract details from the ApproachExplanation for matching
        explanation_approach_name = approach_explanation.approach_name.lower()
        # Combine explanation and algorithm details for richer keyword matching
        explanation_keywords_text = (approach_explanation.explanation + " " +
                                     approach_explanation.algorithm_details).lower()
        explanation_time = approach_explanation.time_complexity
        explanation_space = approach_explanation.space_complexity
        explanation_correct = approach_explanation.correct_implementation
        explanation_issues = approach_explanation.issues_identified

       

        

        augmented_results = []
        # Define augmentation parameters
        GENERAL_NAME_BOOST = 0.05 # Reduced boost, specificity is key
        SPECIFICITY_MAX_BONUS = 0.15 # Max possible bonus from matching rubric points
        IMPLEMENTATION_PENALTY = 0.20

        for result in approach_results:
            current_result = result.copy() # Work on a copy
            approach_key = current_result.get('approach')

            # Skip processing if essential info is missing
            if not approach_key:
                logger.warning("Skipping augmentation for result missing 'approach' key: %s", result)
                augmented_results.append(current_result) # Keep original result
                continue

            approach_details = parsed_rubric["approaches"].get(approach_key)
            if not approach_details:
                logger.warning(f"Could not find details for approach '{approach_key}' in parsed rubric during augmentation. Skipping augmentation for this result.")
                augmented_results.append(current_result) # Keep original result
                continue

            approach_full_name = approach_details.get("name", "").lower()
            initial_confidence = current_result.get('confidence', 0.0)
            current_confidence = initial_confidence
            augmentation_log = [] # Track changes for logging

            

            # --- 1. General Approach Name Boost (Minor) ---
            if explanation_approach_name and explanation_approach_name in approach_full_name:
                boost = GENERAL_NAME_BOOST
                new_confidence = min(1.0, current_confidence + boost)
                if new_confidence > current_confidence:
                    augmentation_log.append(f"General name match boost: {current_confidence:.3f} -> {new_confidence:.3f} (+{boost:.2f})")
                    current_confidence = new_confidence
            else:
                 augmentation_log.append("No general name match.")

            # --- 2. Specificity Boost based on Rubric Points ---
            specificity_bonus = 0.0
            matched_points_count = 0
            rubric_points = approach_details.get("points", [])
            if rubric_points: # Avoid division by zero if no points
                bonus_per_point = SPECIFICITY_MAX_BONUS / len(rubric_points)
                num_matched_keywords_total = 0

                for point in rubric_points:
                    point_desc = point.get("description", "").lower()
                    # Extract potential keywords (alphanumeric, >= 4 chars)
                    keywords = set(re.findall(r'\b[a-zA-Z0-9]{4,}\b', point_desc))
                    # Optional: Refine keywords - remove very common programming terms if needed
                    # keywords -= {'loop', 'array', 'index', 'value', 'search', 'return', ...}

                    point_matched = False
                    matched_keywords_for_point = []
                    for keyword in keywords:
                        if keyword in explanation_keywords_text:
                            num_matched_keywords_total += 1
                            matched_keywords_for_point.append(keyword)
                            point_matched = True
                            # Simple: Give bonus if *any* keyword from the point matches the explanation
                    if point_matched:
                         specificity_bonus += bonus_per_point
                         matched_points_count += 1
                         # augmentation_log.append(f"  Point match: '{point_desc[:30]}...' (Keywords: {matched_keywords_for_point})")


                specificity_bonus = min(specificity_bonus, SPECIFICITY_MAX_BONUS) # Cap the total bonus
                if specificity_bonus > 0:
                    new_confidence = min(1.0, current_confidence + specificity_bonus)
                    if new_confidence > current_confidence:
                       augmentation_log.append(f"Specificity bonus ({matched_points_count}/{len(rubric_points)} points matched, {num_matched_keywords_total} keywords): {current_confidence:.3f} -> {new_confidence:.3f} (+{specificity_bonus:.3f})")
                       current_confidence = new_confidence
                else:
                    augmentation_log.append("No specific point keywords matched explanation.")
            else:
                augmentation_log.append("No rubric points found for specificity check.")


            current_result['confidence'] = current_confidence # Update confidence after boosts

            # --- 3. Apply Penalties / Add Info ---
            original_explanation = current_result.get('explanation', '')
            added_info = []

            # Complexity Insights
            if explanation_time != 'Unknown' or explanation_space != 'Unknown':
                added_info.append(f"Complexity Insights (from code analysis): Time={explanation_time}, Space={explanation_space}")
                augmentation_log.append("Added complexity insights.")

            # Implementation Correctness Penalty
            if not explanation_correct:
                penalty = IMPLEMENTATION_PENALTY
                old_confidence = current_result['confidence']
                current_result['confidence'] = max(0.0, old_confidence - penalty) # Ensure confidence doesn't go below 0
                augmentation_log.append(f"Implementation issue penalty: {old_confidence:.3f} -> {current_result['confidence']:.3f} (-{penalty:.2f})")
                added_info.append("Warning: Code analysis identified potential implementation issues.")

            # Identified Issues Info
            if explanation_issues:
                issues_str = "\n".join(f"- {issue}" for issue in explanation_issues)
                added_info.append(f"Issues Identified (from code analysis):\n{issues_str}")
                augmentation_log.append(f"Added {len(explanation_issues)} identified issues.")

            # Combine original explanation with added info
            if added_info:
                 current_result['explanation'] = original_explanation + "\n\n--- Augmentation Notes ---\n" + "\n".join(added_info)
            else:
                 current_result['explanation'] = original_explanation # Keep original if no info added

            # --- Final Logging for this approach ---
            

            augmented_results.append(current_result) # Add the processed result


        
        for result in augmented_results:
            # Use .get with defaults for safer access
            approach = result.get('approach', 'Unknown Approach')
            confidence = result.get('confidence', 0.0)
            

        
        return augmented_results
    
    async def _evaluate_single_approach(
        self,
        problem_statement: str,
        approach_name: str,
        approach_details: Dict[str, Any],
        sanitized_solution_code: str,
        model_solution: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single approach against the student solution
        
        Args:
            problem_statement: The problem statement
            approach_name: Name of the approach being evaluated
            approach_details: Details of the approach
            sanitized_solution_code: The sanitized student's solution code
            model_solution: Optional model solution
            
        Returns:
            Evaluation result with confidence
        """
        logger.info(f"Evaluating approach: {approach_name}")
        
        # Format approach description
        approach_description = f"{approach_name}: {approach_details['name']}\n"
        
        for i, point in enumerate(approach_details["points"]):
            approach_description += f"  {i+1}. {point['description']} [{point['marks']} marks]\n"
        
        # Create prompt for evaluating this specific approach
        # Handle model solutions (which could be a single string or a list)
        model_solutions_text = ""
        if model_solution:
            if isinstance(model_solution, list):
                for i, solution in enumerate(model_solution):
                    model_solutions_text += f"MODEL SOLUTION {i+1}:{nl}```{nl}{solution}{nl}```{nl}{nl}"
            else:
                model_solutions_text = f"MODEL SOLUTION:{nl}```{nl}{model_solution}{nl}```{nl}"
        
        
        evaluation_prompt = f"""
        You are an expert code evaluator specializing in identifying programming approaches.

        PROBLEM STATEMENT:
        ```
        {problem_statement}
        ```

        YOU ARE EVALUATING THE FOLLOWING APPROACH ONLY:
        {approach_description}

        STUDENT SOLUTION (SANITIZED):
        ```
        {sanitized_solution_code}
        ```

        
        MATCH THE STUDENT'S SOLUTION TO THE RUBRIC BASED ON THE APPROACHES DESCRIBED BELOW .
        {model_solutions_text}
        INSTRUCTIONS:
        1. Analyze the student's solution carefully, focusing on the algorithm and implementation style
        2. Determine how well it matches the specific approach description above, you can take reference from one of the model solution from the given model solutions
        3. Consider algorithm characteristics like time complexity, space usage, and implementation pattern
        4. Identify specific evidence in the code that supports or contradicts this approach
        5. You are ONLY evaluating this ONE approach - you don't know about any other possible approaches
        6. Be objective and thorough in your analysis
        7. Provide a confidence score between 0.0 and 1.0 indicating how well the solution matches this approach
        8. Confidence score can be anything like 0.15, 0.8 etc, no need to keep it a multiple of 0.1
        RESPONSE FORMAT:
        Return a JSON object with the following structure:
        {{
            "approach": "{approach_name}",
            "confidence": 0.0-1.0 (anything like 0.15, 0.8 etc, no need to keep it a multiple of 0.1),
            "explanation": "Detailed explanation with specific code evidence for why this confidence level was assigned",
            "key_indicators": ["List of specific code patterns that indicate this approach"]
        }}
        
        The confidence score should reflect how likely it is that the student's solution follows this approach:
        - 0.8-1.0: Strong match with clear evidence
        - 0.5-0.8: Moderate match with some differences
        - 0.3-0.5: Weak match with significant differences
        - 0.0-0.3: Very poor match, fundamentally different approach

        Only return the JSON object and nothing else.
        """
        try:
            # Query the LLM
            response = await query_llm(evaluation_prompt, temperature=0.1)
            
            # Extract JSON from response
            json_match = re.search(r'(\{.*\})', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
            else:
                result = json.loads(response)
            
            # Ensure approach name is correct
            result["approach"] = approach_name
            
            # Log the confidence score for debugging
            logger.info(f"Initial confidence for {approach_name}: {result.get('confidence', 0)}")
            logger.info(f"Key indicators for {approach_name}: {result.get('key_indicators', [])}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error evaluating approach {approach_name}: {str(e)}", exc_info=True)
            return {
                "approach": approach_name,
                "confidence": 0.0,
                "explanation": f"Error during evaluation: {str(e)}",
                "key_indicators": []
            }

    
    async def _evaluate_approaches_in_parallel(
        self,
        problem_statement: str,
        parsed_rubric: Dict[str, Any],
        sanitized_solution_code: str,
        model_solution: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all approaches in parallel
        
        Args:
            problem_statement: The problem statement
            parsed_rubric: Parsed rubric structure
            sanitized_solution_code: The sanitized student's solution code
            model_solution: Optional model solution
            
        Returns:
            List of evaluation results for each approach
        """
        tasks = []
        
        # Create a task for each approach
        for approach_name, approach_details in parsed_rubric["approaches"].items():
            
            task = self._evaluate_single_approach(
                problem_statement,
                approach_name,
                approach_details,
                sanitized_solution_code,
                model_solution
            )
            tasks.append(task)
        
        # Run all tasks in parallel
        results = await asyncio.gather(*tasks)
        
        return results
    
    def _select_best_approach(
        self,
        approach_results: List[Dict[str, Any]],
        parsed_rubric: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Select the best approach based on confidence scores, with tie-breaking consideration.
        Structure remains compatible: returns Dict[str, Any] for the best approach.

        Args:
            approach_results: Results from parallel approach evaluations (potentially augmented).
            parsed_rubric: Parsed rubric structure (used for fallback).

        Returns:
            The selected best approach dictionary including 'approach', 'confidence', 'explanation', 'key_indicators'.
        """
        logger.info("Selecting best approach from %d results:", len(approach_results))

        # Handle empty results - return a valid fallback structure
        if not approach_results:
             fallback_approach_name = next(iter(parsed_rubric.get("approaches", {"fallback": {}}).keys()), "unknown")
             logger.warning("No approach results provided to select from. Falling back to first defined approach: %s", fallback_approach_name)
             # Ensure the fallback return dictionary has the expected keys
             return {
                 "approach": fallback_approach_name,
                 "confidence": 0.05, # Assign minimal confidence
                 "explanation": "Error: No evaluation results were generated. Using fallback approach.",
                 "key_indicators": []
             }

        # Log initial confidences before sorting
        for result in approach_results:
            approach = result.get("approach", "Unknown Approach")
            confidence = result.get("confidence", 0.0)
            logger.info(f"  Pre-selection score for {approach}: {confidence:.3f}")

        # Sort by confidence score in descending order. Python's sort is stable.
        sorted_results = sorted(approach_results, key=lambda x: x.get("confidence", 0.0), reverse=True)

        best_approach_result = sorted_results[0].copy() # Work with a copy
        best_approach_name = best_approach_result.get("approach", "Unknown Approach")
        best_confidence = best_approach_result.get("confidence", 0.0)
        logger.info(f"Initial top approach identified: '{best_approach_name}' with confidence {best_confidence:.3f}")

        # --- Tie-breaking Consideration & Logging ---
        TIE_THRESHOLD = 0.05 # Define how close scores need to be to log a tie warning
        if len(sorted_results) > 1:
            second_approach_result = sorted_results[1]
            second_approach_name = second_approach_result.get("approach", "Unknown Approach")
            second_confidence = second_approach_result.get("confidence", 0.0)
            confidence_diff = best_confidence - second_confidence

            if confidence_diff < TIE_THRESHOLD:
                tie_note = (
                    f"\n\n--- Selection Note ---\n"
                    f"Confidence score ({best_confidence:.3f}) was very close to the next best approach "
                    f"'{second_approach_name}' ({second_confidence:.3f}, difference: {confidence_diff:.3f}). "
                    f"Selected '{best_approach_name}' due to the slightly higher score after evaluation and augmentation."
                )
                # Append the note to the explanation of the chosen approach
                best_approach_result["explanation"] = best_approach_result.get("explanation", "") + tie_note
                # NOTE: No change in selection here, just logging and annotating.
                # The sorting already picked the highest. If a more complex tie-breaker
                # (e.g., based on specificity points matched) is needed, it would be implemented here.

        # --- Fallback if Best Confidence is Too Low ---
        MIN_ACCEPTABLE_CONFIDENCE = 0.1 # Minimum confidence to accept the LLM's choice
        if best_confidence < MIN_ACCEPTABLE_CONFIDENCE:
            fallback_approach_name = next(iter(parsed_rubric.get("approaches", {"fallback": {}}).keys()), "unknown")
            logger.warning(
                f"Highest confidence ({best_confidence:.3f} for '{best_approach_name}') is below threshold ({MIN_ACCEPTABLE_CONFIDENCE}). "
                f"Falling back to the first defined approach: '{fallback_approach_name}'."
            )
            # Try to find the original (potentially augmented) result for the fallback approach to provide context
            fallback_result = next((r for r in sorted_results if r.get("approach") == fallback_approach_name), None)
            fallback_explanation = f"Reason: Highest confidence {best_confidence:.3f} was too low. "
            if fallback_result:
                fallback_explanation += f"Original evaluation for '{fallback_approach_name}': {fallback_result.get('explanation', 'No details available.')}"
            else:
                 fallback_explanation += f"No evaluation details available for '{fallback_approach_name}'."

            # Return the fallback structure
            return {
                "approach": fallback_approach_name,
                "confidence": 0.05, # Minimal confidence for fallback
                "explanation": fallback_explanation,
                "key_indicators": fallback_result.get("key_indicators", []) if fallback_result else []
            }

        # --- Add Comparison Explanation for the Selected Approach ---
        logger.info(f"Selected final approach: '{best_approach_name}' with confidence {best_confidence:.3f}")
        other_approaches = sorted_results[1:]
        if other_approaches:
            comparison = "\n\n--- Comparison with Other Evaluated Approaches ---\n"
            for other_result in other_approaches:
                other_name = other_result.get("approach", "Unknown")
                other_conf = other_result.get("confidence", 0.0)
                conf_diff = best_confidence - other_conf
                comparison += f"- {other_name}: Confidence {other_conf:.2f} (Difference: {conf_diff:+.2f})\n"
            best_approach_result["explanation"] = best_approach_result.get("explanation", "") + comparison

        # Ensure all necessary keys are present in the final returned dictionary
        final_result = {
            "approach": best_approach_name,
            "confidence": best_confidence,
            "explanation": best_approach_result.get("explanation", "No explanation provided."),
            "key_indicators": best_approach_result.get("key_indicators", [])
        }

        return final_result
    
    async def format_rubric_for_evaluation(self, extracted_rubric: ExtractedRubric) -> str:
        """
        Format the extracted rubric information for use in evaluation.
        
        Args:
            extracted_rubric: The extracted rubric information
            
        Returns:
            Formatted rubric text for evaluation
        """
        # Format standard rubric
        approach = extracted_rubric.approach
        rubric_info = extracted_rubric.rubric
        result = [f"# {approach}: {rubric_info['name']}"]
        
        for i, point in enumerate(rubric_info["points"]):
            result.append(f"{i+1}. {point['description']} [{point['marks']} marks]")
        
        return "\n".join(result)