"""

Math Assistant Agent
Demonstrates ADK's Code Execution built-in tool for calculations.
Reference: https://google.github.io/adk-docs/tools/built-in-tools#code-execution
"""


from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor  # Import code executor

# Create math assistant with code execution

root_agent = LlmAgent(
    model='gemini-2.5-flash', # Must use Gemini 2.0+ for code execution
    name='math_assistant',
    description='Helps users with mathematical calculations and analysis.',
    instruction="""

    You are a math assistant that helps users with calculations and mathematical analysis.
    Your capabilities:
    1. When users ask for calculations, use code execution for precision
    2. Show your work by explaining the calculation steps
    3. Verify results by running the code
    4. Handle complex mathematical operations (statistics, algebra, etc.)
    Always use code execution for numerical calculations to ensure accuracy.
 """,

 code_executor=BuiltInCodeExecutor() # Enable code execution

)

# Test 1 Simple Calculation
# Calculate 15% tip on a $87.50 bill

# Test 2 Complex calculation
# What's the compound interest on $5,000 invested at 6% annual rate for 8 years, compounded monthly?

# Test 3 Data processing
# Calculate the average, median, and standard deviation of these numbers: 12, 15, 18, 20, 22, 25, 28, 30