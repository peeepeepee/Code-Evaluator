# Code Evaluation System

A full-stack code evaluation platform for automated code evaluation using Large Language Models, built with FastAPI.

## Features
- Automated code evaluation
- Built with FastAPI for high performance
- PostgreSQL database integration using SQLAlchemy
- JWT authentication

## Setup & Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables:**
   Create a `.env` file in the root directory and configure your environment variables (e.g., database connection strings, JWT secrets, LLM API keys). You can generate a secret using `python generate_secret.py`.

3. **Initialize the Database:**
   Ensure your database is running and configured in `.env`, then create the tables:
   ```bash
   python create_tables.py
   ```

4. **Run the Application:**
   Start the FastAPI development server:
   ```bash
   python main.py
   ```
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload
   ```

## API Documentation
Once the server is running, you can access the interactive API documentation at:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`
