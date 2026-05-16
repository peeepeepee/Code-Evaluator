#!/usr/bin/env python
"""
Script to generate algorithm evaluation guidance for all problems in the database.
This script is intended to be run periodically to update guidance for new problems.
"""

import asyncio
import argparse
import logging
from pathlib import Path
import sys
from sqlalchemy.orm import Session
project_root = str(Path(__file__).parent.parent.parent)
sys.path.append(project_root)
from app.db.database import get_db, SessionLocal
from app.db.models import Problem
from app.agents.rubric_extractor_agent import RubricExtractorAgent
from app.agents.evaluation_guidance_agent import EvaluationGuidanceAgent
from app.utils.rubric_parser import parse_rubric

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("generate_guidance.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def generate_guidance_for_problem(problem_id: int, force_update: bool = False):
    """
    Generate algorithm guidance for a specific problem
    
    Args:
        problem_id: ID of the problem
        force_update: Whether to force update existing guidance
    """
    db = SessionLocal()
    try:
        # Get the problem from database
        problem = db.query(Problem).filter(Problem.id == problem_id).first()
        if not problem:
            logger.error(f"Problem with ID {problem_id} not found")
            return False
            
        # Check if guidance already exists and we're not forcing an update
        existing_guidance = problem.algorithm_guidance
        if existing_guidance and not force_update:
            logger.info(f"Guidance already exists for problem {problem_id}. Use --force to update.")
            return False
            
        logger.info(f"Generating guidance for problem {problem_id}: {problem.title}")
        
        # Parse rubric to get approaches
        parsed_rubric = parse_rubric(problem.rubric)
        
        # Use rubric extractor to identify best approach
        rubric_extractor = RubricExtractorAgent()
        for approach_name, approach_details in parsed_rubric["approaches"].items():
            logger.info(f"Extracting rubric for approach: {approach_name}")
            
            # Create a simulated extracted rubric since we're not analyzing student code
            extracted_rubric = {
                "approach": approach_name,
                "rubric": approach_details,
                "explanation": approach_details["name"],
                "is_custom": False
            }
            
            # Generate guidance for this approach
            guidance_agent = EvaluationGuidanceAgent()
            try:
                guidance = await guidance_agent.generate_evaluation_guidance(
                    problem.problem_description,
                    extracted_rubric,
                    db,
                    problem.id
                )
                
                logger.info(f"Successfully generated guidance for problem {problem_id}")
                return True
                
            except Exception as e:
                logger.error(f"Error generating guidance for problem {problem_id}: {str(e)}")
                return False
                
    except Exception as e:
        logger.error(f"Error processing problem {problem_id}: {str(e)}")
        return False
    finally:
        db.close()

async def generate_all_guidance(force_update: bool = False, problem_id: int = None):
    """
    Generate guidance for all problems or a specific problem
    
    Args:
        force_update: Whether to force update existing guidance
        problem_id: Optional specific problem ID to generate guidance for
    """
    db = SessionLocal()
    try:
        if problem_id:
            # Generate for specific problem
            await generate_guidance_for_problem(problem_id, force_update)
        else:
            # Get all problems
            problems = db.query(Problem).all()
            logger.info(f"Found {len(problems)} problems in the database")
            
            # Process each problem
            successful = 0
            for problem in problems:
                result = await generate_guidance_for_problem(problem.id, force_update)
                if result:
                    successful += 1
                
            logger.info(f"Generated guidance for {successful} out of {len(problems)} problems")
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description='Generate algorithm guidance for problems')
    parser.add_argument('--force', action='store_true', help='Force update existing guidance')
    parser.add_argument('--problem-id', type=int, help='Generate for specific problem ID')
    
    args = parser.parse_args()
    
    asyncio.run(generate_all_guidance(args.force, args.problem_id))
    
if __name__ == "__main__":
    main()