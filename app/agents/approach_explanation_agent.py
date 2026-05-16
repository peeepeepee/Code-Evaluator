import logging
import json
import re
import html
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from app.utils.llm_utils import query_llm
from app.utils.sanitizer import process_inputs, extract_language_from_code, remove_java_comments

logger = logging.getLogger(__name__)

class ApproachExplanation(BaseModel):
    """Schema for the code approach explanation"""
    approach_name: str = Field("Unknown approach", description="Brief name of the algorithm/approach")
    explanation: str = Field("", description="Detailed step-by-step explanation of the code")
    algorithm_details: str = Field("", description="Description of the algorithm(s) used")
    time_complexity: str = Field("Unknown", description="Big O analysis of time complexity")
    space_complexity: str = Field("Unknown", description="Big O analysis of space complexity")
    issues_identified: List[str] = Field([], description="List of issues without suggested fixes")
    correct_implementation: bool = Field(False, description="Whether the implementation is correct")

class ApproachExplanationAgent:
    """
    Agent that analyzes student code and provides a step-by-step explanation
    of the approach used, along with identification of any issues without suggesting fixes.
    """
    
    async def explain_approach(self, student_code: str, problem_statement: Optional[str] = None) -> ApproachExplanation:
        """
        Analyze the student's code and provide a detailed explanation of the approach used,
        identifying any issues without suggesting fixes.
        
        Args:
            student_code: The student's code submission
            problem_statement: Optional problem statement for context
            
        Returns:
            ApproachExplanation with details of the approach and issues
        """
        try:
            # Try to detect the programming language
            language = extract_language_from_code(student_code)
            
            # Unescape any HTML entities in the code before analysis
            unescaped_code = html.unescape(student_code)
            
            # Sanitize the code without HTML escaping
            # We're manually using the unescaped version for analysis
            _, _, sanitized_code = process_inputs("", "", unescaped_code)
            
            # Set up problem statement section if provided
            problem_section = ""
            if problem_statement:
                problem_section = f"PROBLEM STATEMENT:\n```\n{problem_statement}\n```\n"
            
            # JSON format template
            json_format = """{
                "approach_name": "Brief name of the algorithm/approach",
                "explanation": "Detailed step-by-step explanation of the code",
                "algorithm_details": "Description of the algorithm(s) used",
                "time_complexity": "Big O analysis of time complexity",
                "space_complexity": "Big O analysis of space complexity",
                "issues_identified": ["List of issues without suggested fixes"],
                "correct_implementation": true/false
            }"""
            
            # Create a prompt for approach explanation
            unescaped_code = remove_java_comments(unescaped_code)
            explanation_prompt = f"""
            You are an expert code analyzer. Your task is to thoroughly analyze the given code and explain the approach
            it implements step-by-step. Do NOT suggest improvements or fixes; only identify issues if they exist.
            
            {problem_section}
            
            STUDENT CODE ({language}):
            ```
            {unescaped_code}
            ```
            
            INSTRUCTIONS:
            1. Provide a detailed step-by-step explanation of how the code works
            2. Identify the algorithm(s) or data structure(s) being used
            3. Explain the overall approach and logic flow
            4. Calculate the time and space complexity of the implementation
            5. Identify any logical errors or edge cases not handled properly
            6. Flag any syntax errors or implementation issues
            7. Do NOT suggest fixes or improvements - only identify issues
            8. Focus on what the code ACTUALLY DOES, not what it's supposed to do
            9. Do NOT flag HTML entity issues (like &lt; or &gt;) as these are display artifacts, not code issues
            
            FORMAT YOUR ANALYSIS AS A JSON OBJECT WITH THE FOLLOWING FIELDS:
            {json_format}
            
            Return only the JSON object and nothing else.
            """
            
            # Query LLM for approach explanation
            response = await query_llm(explanation_prompt, temperature=0.2)
            
            # Parse the response
            try:
                # Try to extract JSON from the response
                json_match = re.search(r'(\{.*\})', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    approach_explanation_dict = json.loads(json_str)
                else:
                    approach_explanation_dict = json.loads(response)
                
                # Filter out any issues related to HTML entities
                if "issues_identified" in approach_explanation_dict:
                    filtered_issues = [
                        issue for issue in approach_explanation_dict["issues_identified"]
                        if not any(term in issue.lower() for term in ["html", "entity", "&lt;", "&gt;", "escaped"])
                    ]
                    approach_explanation_dict["issues_identified"] = filtered_issues
                    
                    # Update correct_implementation based on remaining issues
                    approach_explanation_dict["correct_implementation"] = len(filtered_issues) == 0
                
                # Convert to Pydantic model
                approach_explanation = ApproachExplanation(**approach_explanation_dict)
                
                logger.info(f"Generated approach explanation for: {approach_explanation.approach_name}")
                return approach_explanation
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse approach explanation response: {response}")
                # Fall back to a simpler format
                return ApproachExplanation(
                    approach_name="Unknown approach",
                    explanation="Could not generate a structured explanation of the code.",
                    algorithm_details="Unknown algorithm",
                    time_complexity="Unknown",
                    space_complexity="Unknown",
                    issues_identified=["Failed to analyze the code properly"],
                    correct_implementation=False
                )
                
        except Exception as e:
            logger.error(f"Error explaining approach: {str(e)}", exc_info=True)
            return ApproachExplanation(
                approach_name="Analysis Error",
                explanation=f"Error analyzing code: {str(e)}",
                algorithm_details="Unknown",
                time_complexity="Unknown",
                space_complexity="Unknown",
                issues_identified=[f"Error during analysis: {str(e)}"],
                correct_implementation=False
            )
    
    def format_approach_explanation(self, approach_explanation: ApproachExplanation) -> str:
        """
        Format the approach explanation for inclusion in an evaluator prompt.
        
        Args:
            approach_explanation: The approach explanation
            
        Returns:
            Formatted explanation text for the evaluator
        """
        # Handle issues list formatting
        issues_text = "None identified"
        if approach_explanation.issues_identified:
            issues_text = "- " + "\n- ".join(approach_explanation.issues_identified)
        
        # Implementation status text
        implementation_status = "Correct implementation" if approach_explanation.correct_implementation else "Has implementation issues"
        
        formatted_text = f"""
        STUDENT'S APPROACH ANALYSIS:
        ---------------------------
        Approach: {approach_explanation.approach_name}
        
        Explanation:
        {approach_explanation.explanation}
        
        Algorithm Details:
        {approach_explanation.algorithm_details}
        
        Complexity:
        - Time: {approach_explanation.time_complexity}
        - Space: {approach_explanation.space_complexity}
        
        Implementation Status: {implementation_status}
        
        Issues Identified:
        {issues_text}
        """
        
        return formatted_text