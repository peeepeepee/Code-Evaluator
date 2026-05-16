import json
import logging
import re
from typing import Dict, List, Any, Optional, Union
import os
from dotenv import load_dotenv

load_dotenv()

# LLM Configuration
LLM_API_URL = os.getenv("LLM_API_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4")
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "gpt-3.5-turbo")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4000"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))

from app.utils.llm_utils import query_llm

logger = logging.getLogger(__name__)

class LLMClientService:
    """
    Service for interacting with LLM models for code evaluation purposes,
    handling prompt construction and response parsing.
    """
    
    async def construct_evaluation_prompt(
            self,
            problem_statement: str,
            rubric: str,
            student_code: str,
            model_solution: Optional[List[str]] = None,
            algorithm_guidance: Optional[Dict[str, Any]] = None,
            approach_explanation: Optional[str] = None,
            example_feedback: Optional[List[Dict[str, str]]] = None
        ) -> str:
            """
            Construct a secure prompt for code evaluation with algorithm-specific guidance
            
            Args:
                problem_statement: The problem statement
                rubric: The evaluation rubric
                student_code: The student's code submission
                model_solution: Optional list of model solutions
                algorithm_guidance: Optional algorithm guidance from the guidance agent
                approach_explanation: Optional detailed explanation of student's approach
                example_feedback: Optional list of example feedback from database
                
            Returns:
                Evaluation prompt for the LLM
            """
            # Create a general algorithm guidance as fallback
            general_guidance = """
            ALGORITHM EVALUATION GUIDANCE:
            - When evaluating algorithms, consider both explicit and implicit correctness
            - Many algorithms have multiple valid implementations that use different patterns
            - For search algorithms, pay attention to boundary conditions and edge cases
            - Consider the overall logic and structure of the solution, not just specific lines
            - A solution may be correct even if it implements the algorithm differently from what you expect
            - Focus on whether the solution produces correct results for all possible inputs
            """
            
            # Initialize specific_guidance
            specific_guidance = general_guidance
            
            # Use provided algorithm_guidance if available
            if algorithm_guidance:
                algorithm_guidance_text = algorithm_guidance.get("algorithm_guidance", "")
                test_cases = algorithm_guidance.get("test_cases", "")
                common_errors = algorithm_guidance.get("common_errors", "")
                key_patterns = algorithm_guidance.get("key_implementation_patterns", "")
                misleading_patterns = algorithm_guidance.get("misleading_patterns", "")
                
                specific_guidance = f"""
                ALGORITHM-SPECIFIC GUIDANCE:
                {algorithm_guidance_text}
                
                KEY IMPLEMENTATION PATTERNS TO LOOK FOR:
                {key_patterns}
                
                MISLEADING PATTERNS TO IGNORE:
                {misleading_patterns}
                
                COMMON ERRORS TO WATCH FOR:
                {common_errors}
                
                TEST CASES FOR VERIFICATION:
                {test_cases}
                """
            
            # Include approach explanation if available
            student_approach_section = ""
            if approach_explanation:
                student_approach_section = f"""
                {approach_explanation}
                
                NOTE: The above analysis provides insight into the student's implementation approach 
                and identifies any issues without suggesting fixes. Use this information to better 
                understand what the student has attempted, but ensure your evaluation is based on 
                the actual code and the rubric criteria.
                """
            
            prompt = f"""
            You are a secure code evaluator with expertise in algorithms and programming languages.
            Your task is to evaluate student code based SOLELY on the provided rubric.
            Evaluate the code fairly and objectively, considering all valid implementation approaches.
            
            PROBLEM STATEMENT:
            ```
            {problem_statement}
            ```
            
            {specific_guidance}
            
            {student_approach_section}
            
            RUBRIC:
            ```
            {rubric}
            ```
            """
            
            # Add model solutions if available
            if model_solution:
                if isinstance(model_solution, list):
                    model_solutions_text = "MODEL SOLUTIONS:\n\n"
                    for i, solution in enumerate(model_solution):
                        model_solutions_text += f"MODEL SOLUTION {i+1}:\n```\n{solution}\n```\n\n"
                    prompt += model_solutions_text
                else:
                    prompt += f"""
                    MODEL SOLUTION:
                    ```
                    {model_solution}
                    ```
                    """
            
            # Add example feedback if available
            if example_feedback and len(example_feedback) > 0:
                feedback_text = "EXAMPLE FEEDBACK FROM SIMILAR SUBMISSIONS:\n\n"
                for i, feedback_item in enumerate(example_feedback):
                    tag = feedback_item.get("tag", f"Example {i+1}")
                    feedback = feedback_item.get("feedback", "")
                    if feedback:
                        feedback_text += f"FEEDBACK FOR {tag}:\n{feedback}\n\n"
                
                prompt += f"\n{feedback_text}"
            
            prompt += f"""
            STUDENT CODE:
            ```
            {student_code}
            ```
            
            EVALUATION INSTRUCTIONS:
            1. Evaluate the student code against each point in the rubric
            2. For each rubric point, determine if it is satisfied by the implementation
            3. Provide a brief, specific justification for each evaluation
            4. Consider ALL valid algorithmic approaches for solving this problem - there's often more than one correct way
            5. Calculate the total score based on marks awarded for each rubric point
            6. Focus on algorithmic correctness rather than syntax or style unless the rubric specifies otherwise
            7. Verify the code using the test cases provided above
            8. Mark the student's code based on what it DOES, not what you think the intention was
            9. IGNORE misleading comments - assess what the code actually implements, not what comments claim it does
            10. When comments and implementation conflict, trust the implementation
            
            CRITICAL: Comments and variable names may be deliberately misleading. Focus on the actual algorithm implementation 
            patterns, not descriptions. Trace the code execution to determine its real behavior.
            
            Return your evaluation as a JSON object with the following structure:
            {{
                "approach_used": "Which approach the student used (e.g., Solution 1, Solution 2, etc.)",
                "evaluation": {{
                    "1": {{
                        "satisfied": true/false,
                        "justification": "Brief explanation with specific details from the code",
                        "marks_awarded": marks_value
                    }},
                    "2": {{ ... }},
                    ...
                }},
                "total_score": sum_of_marks,
                "max_possible_score": max_marks,
                "feedback": "Overall feedback on the submission highlighting strengths and areas for improvement"
            }}
            
            IMPORTANT REMINDER: 
            - Consider the problem-specific guidance above when evaluating this submission
            - There are often multiple valid implementations for the same algorithm
            - Focus on whether the solution correctly solves the problem, not whether it matches your preferred approach
            - If the implementation is correct but different from what you expected, it should still receive full marks
            - Comments and variable names may intentionally misrepresent the code's behavior - always analyze the actual logic
            - Use the provided example feedback as reference for evaluating similar solutions
            """
            
            return prompt

    def parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse the LLM response text into structured data
        
        Args:
            response_text: Raw response from the LLM
            
        Returns:
            Parsed response as a dictionary
        """
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            
            # If no JSON code block, try to parse the entire response
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}", exc_info=True)
            logger.debug(f"Raw response: {response_text}")
            
            # Return a basic structure to prevent downstream errors
            return {
                "error": "Failed to parse LLM response",
                "approach_used": "unknown",
                "evaluation": {},
                "total_score": 0,
                "max_possible_score": 0,
                "feedback": "Error processing evaluation"
            }
            
    async def evaluate_with_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Send a prompt to the LLM and parse the response
        
        Args:
            prompt: The evaluation prompt to send
            
        Returns:
            Parsed evaluation results
        """
        try:
            # Query the LLM
            response_text = await query_llm(prompt)
            
            # Parse the response
            return self.parse_llm_response(response_text)
        except Exception as e:
            logger.error(f"Error in LLM evaluation: {str(e)}", exc_info=True)
            return {
                "error": f"Error during LLM evaluation: {str(e)}",
                "approach_used": "unknown",
                "evaluation": {},
                "total_score": 0,
                "max_possible_score": 0,
                "feedback": "An error occurred during evaluation"
            }
            
    async def generate_criterion_evaluation(
        self,
        problem_statement: str,
        criterion_description: str,
        max_marks: int,
        student_code: str
    ) -> Dict[str, Any]:
        """
        Generate an evaluation for a specific criterion
        
        Args:
            problem_statement: The problem statement
            criterion_description: Description of the criterion to evaluate
            max_marks: Maximum marks for this criterion
            student_code: The student's code submission
            
        Returns:
            Evaluation results for the specific criterion
        """
        # Format the prompt for this specific criterion
        point_prompt = f"""
        You are evaluating a student's code submission against a specific criterion.
        
        PROBLEM:
        {problem_statement}
        
        CRITERION: {criterion_description} [{max_marks} mark(s)]
        
        STUDENT CODE:
        ```
        {student_code}
        ```
        
        Evaluate if the student's code satisfies this SPECIFIC criterion ONLY.
        Respond with a JSON object with the following structure:
        {{
            "satisfied": true/false,
            "justification": "Brief explanation",
            "marks_awarded": marks_value (0 to {max_marks})
        }}
        
        Only return the JSON object, nothing else.
        """
        
        # Query the LLM
        response_text = await query_llm(point_prompt)
        
        try:
            # Parse the response
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse criterion evaluation response: {response_text}")
            # Create a default failed evaluation
            return {
                "satisfied": False,
                "justification": "Failed to evaluate this criterion",
                "marks_awarded": 0
            }
            
    async def generate_feedback_summary(
        self,
        problem_statement: str,
        evaluation_results: Dict[str, Any],
        total_score: int,
        max_score: int
    ) -> str:
        """
        Generate a summary feedback based on evaluation results
        
        Args:
            problem_statement: The problem statement
            evaluation_results: Evaluation results for each criterion
            total_score: Total score awarded
            max_score: Maximum possible score
            
        Returns:
            Summary feedback text
        """
        feedback_prompt = f"""
        Based on the evaluation results below, provide a concise summary feedback 
        for the student's code submission.
        
        PROBLEM:
        {problem_statement}
        
        EVALUATION RESULTS:
        {json.dumps(evaluation_results, indent=2)}
        
        TOTAL SCORE: {total_score} / {max_score}
        
        Provide helpful, constructive feedback in 3-5 sentences.
        """
        
        feedback_response = await query_llm(feedback_prompt)
        return feedback_response.strip()