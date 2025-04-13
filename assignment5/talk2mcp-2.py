import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import asyncio
from google import genai
from concurrent.futures import TimeoutError
from functools import partial
import re

# Load environment variables from .env file
load_dotenv()

# Global variables
max_iterations = 10
last_response = None
iteration = 0
iteration_response = []

def initialize_environment():
    """Initialize environment and setup Gemini client"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    return genai.Client(api_key=api_key)

async def get_available_tools(session):
    """Fetch and process available tools from MCP"""
    print("Requesting tool list...")
    tools_result = await session.list_tools()
    tools = tools_result.tools
    print(f"Successfully retrieved {len(tools)} tools")
    return tools

def format_tool_descriptions(tools):
    """Format tool information into readable descriptions"""
    tools_description = []
    for i, tool in enumerate(tools):
        try:
            params = tool.inputSchema
            desc = getattr(tool, 'description', 'No description available')
            name = getattr(tool, 'name', f'tool_{i}')
            
            if 'properties' in params:
                param_details = []
                for param_name, param_info in params['properties'].items():
                    param_type = param_info.get('type', 'unknown')
                    param_details.append(f"{param_name}: {param_type}")
                params_str = ', '.join(param_details)
            else:
                params_str = 'no parameters'

            tool_desc = f"{i+1}. {name}({params_str}) - {desc}"
            tools_description.append(tool_desc)
            print(f"Added description for tool: {tool_desc}")
        except Exception as e:
            print(f"Error processing tool {i}: {e}")
            tools_description.append(f"{i+1}. Error processing tool")
    
    return "\n".join(tools_description)

def create_system_prompt(tools_description):
    """Generate the system prompt with tool descriptions"""
    return f"""You are a math agent solving problems in step by step iterations.
You have access to various mathematical tools.
You also have access to a paint application.
You can use the paint application to draw rectangles and add text.

Before each step, think carefully about what needs to be done and explain your reasoning to yourself.
For each operation, identify the type of reasoning you're using (e.g., arithmetic, string manipulation, visualization).

Follow these steps for every operation:
1. Identify the type of operation needed (arithmetic/string/visual)
2. Choose the appropriate tool
3. Verify input parameters are valid
4. Execute the operation
5. Validate the result makes sense before proceeding

If you want to display anything in paint use the following steps:-
    1. You should open_paint tool
    2. You should collect the text to be displayed and use the add_text_in_paint tool to display the text.
    3. You should use the draw_rectangle tool to draw the rectangle around the text.

Available tools:
{tools_description}

You must respond with EXACTLY ONE line in one of these formats (no additional text):
1. For function calls:
   FUNCTION_CALL: function_name|param1|param2|...
   
2. For final answers:
   FINAL_ANSWER: [number]

3. For error or uncertainty:
   ERROR: [error_type]|[description]
   UNCERTAIN: [reason]|[next_steps]

Important:
- When a function returns multiple values, you need to process all of them
- Only give FINAL_ANSWER when you have completed all necessary calculations and verified the result
- Do not repeat function calls with the same parameters
- If you're uncertain about a step or encounter an error:
  * Report it using the ERROR or UNCERTAIN format
  * Suggest alternative approaches if possible
  * Request clarification if needed

Before giving a final answer:
- Verify all calculations are complete
- Check that the result is within reasonable bounds
- Ensure all necessary steps were performed
- Validate the answer format

Examples:
- FUNCTION_CALL: add|5|3
- FUNCTION_CALL: strings_to_chars_to_int|INDIA
- FUNCTION_CALL: draw_rectangle|540|700|1080|1440
- FUNCTION_CALL: add_text_in_paint|Hello
- FINAL_ANSWER: [42]
- ERROR: INVALID_INPUT|Number too large for calculation
- UNCERTAIN: AMBIGUOUS_OPERATION|Need clarification on operation order

DO NOT include any explanations or additional text.
Your entire response should be a single line starting with either FUNCTION_CALL:, FINAL_ANSWER:, ERROR:, or UNCERTAIN:"""

def reset_state():
    """Reset all global variables to their initial state"""
    global last_response, iteration, iteration_response
    last_response = None
    iteration = 0
    iteration_response = []

async def generate_with_timeout(client, prompt, timeout=10):
    """Generate content with a timeout"""
    print("Starting LLM generation...")
    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        print("LLM generation completed")
        return response
    except TimeoutError:
        print("LLM generation timed out!")
        raise
    except Exception as e:
        print(f"Error in LLM generation: {e}")
        raise

def parse_response(response_text):
    """Parse response text into type and content"""
    if not isinstance(response_text, str):
        raise ValueError("Response text must be a string")
    
    parts = response_text.strip().split(":", 1)
    if len(parts) != 2:
        raise ValueError("Invalid response format")
    
    response_type, content = parts
    return response_type.strip(), content.strip()

def parse_function_call(response_text):
    """Parse function call string into components"""
    parts = [p.strip() for p in response_text.split("|")]
    return parts[0], parts[1:]

def parse_error_uncertain(response_text):
    """Parse error or uncertain response into components"""
    parts = response_text.split("|", 1)
    if len(parts) != 2:
        return parts[0], ""
    return parts[0].strip(), parts[1].strip()

def prepare_tool_arguments(tool, params):
    """Convert parameters according to tool schema"""
    arguments = {}
    schema_properties = tool.inputSchema.get('properties', {})
    
    for param_name, param_info in schema_properties.items():
        if not params:
            raise ValueError(f"Not enough parameters provided for {tool.name}")
            
        value = params.pop(0)
        param_type = param_info.get('type', 'string')
        
        if param_type == 'integer':
            arguments[param_name] = int(value)
        elif param_type == 'number':
            arguments[param_name] = float(value)
        elif param_type == 'array':
            if isinstance(value, str):
                value = value.strip('[]').split(',')
            arguments[param_name] = [int(x.strip()) for x in value]
        else:
            arguments[param_name] = str(value)
    
    return arguments

async def execute_tool(session, func_name, arguments):
    """Execute tool and handle results"""
    result = await session.call_tool(func_name, arguments=arguments)
    
    if hasattr(result, 'content'):
        if isinstance(result.content, list):
            return [item.text if hasattr(item, 'text') else str(item) for item in result.content]
        return str(result.content)
    return str(result)

def format_tool_result(result):
    """Format tool execution results"""
    if isinstance(result, list):
        return f"[{', '.join(result)}]"
    return str(result)

async def handle_final_answer(session, response_text):
    """Handle final answer with validation"""
    try:
        # Extract the number from FINAL_ANSWER: [number]
        match = re.search(r'\[(.*?)\]', response_text)
        if not match:
            print("Invalid FINAL_ANSWER format: No brackets found")
            return
        
        number = match.group(1).strip()
        
        # Basic validation
        if not number:
            print("Invalid FINAL_ANSWER: Empty result")
            return
            
        try:
            # Try to convert to number if possible
            float(number)
        except ValueError:
            # If not a number, verify it's not empty or just whitespace
            if not number.strip():
                print("Invalid FINAL_ANSWER: Empty or whitespace")
                return
        
        print(f"Final answer validated: [{number}]")
        
    except Exception as e:
        print(f"Error processing final answer: {e}")
        import traceback
        traceback.print_exc()

async def handle_error(error_type, description):
    """Handle error responses"""
    print(f"\nError encountered: {error_type}")
    print(f"Description: {description}")
    return False  # Changed to False to continue iterations after error

async def handle_uncertain(reason, next_steps):
    """Handle uncertainty in responses"""
    print(f"\nUncertainty reported: {reason}")
    print(f"Suggested next steps: {next_steps}")
    return False  # Continue iterations

async def run_iteration(session, tools, current_query, system_prompt, client):
    """Handle single iteration of the problem-solving process"""
    global iteration, last_response, iteration_response
    
    print(f"\n--- Iteration {iteration + 1} ---")
    prompt = f"{system_prompt}\n\nQuery: {current_query}"
    
    try:
        response = await generate_with_timeout(client, prompt)
        response_text = response.text.strip()
        print(f"LLM Response: {response_text}")
        
        # Parse the response
        response_type, content = parse_response(response_text)
        
        if response_type == "FUNCTION_CALL":
            func_name, params = parse_function_call(content)
            
            # Find the matching tool
            tool = next((t for t in tools if t.name == func_name), None)
            if not tool:
                iteration_response.append(f"Error: Tool not found: {func_name}")
                return await handle_error("UNKNOWN_TOOL", f"Tool not found: {func_name}")
            
            try:
                # Execute the tool
                arguments = prepare_tool_arguments(tool, params)
                result = await execute_tool(session, func_name, arguments)
                result_str = format_tool_result(result)
                
                # Validate result
                if result_str is None or result_str == "":
                    iteration_response.append(f"Error: Empty result from {func_name}")
                    return await handle_error("INVALID_RESULT", f"Empty result from {func_name}")
                
                # Update iteration state
                iteration_response.append(
                    f"In the {iteration + 1} iteration you called {func_name} with {arguments} parameters, "
                    f"and the function returned {result_str}."
                )
                last_response = result_str
                return False  # Continue iterations
            
            except Exception as e:
                iteration_response.append(f"Error executing {func_name}: {str(e)}")
                return await handle_error("TOOL_EXECUTION_ERROR", str(e))
            
        elif response_type == "FINAL_ANSWER":
            await handle_final_answer(session, response_text)
            return True  # Stop iterations only on final answer
            
        elif response_type == "ERROR":
            error_type, description = parse_error_uncertain(content)
            iteration_response.append(f"Error reported: {error_type} - {description}")
            return await handle_error(error_type, description)
            
        elif response_type == "UNCERTAIN":
            reason, next_steps = parse_error_uncertain(content)
            iteration_response.append(f"Uncertainty reported: {reason} - Next steps: {next_steps}")
            return await handle_uncertain(reason, next_steps)
            
        else:
            iteration_response.append(f"Invalid response type: {response_type}")
            return await handle_error("INVALID_RESPONSE_TYPE", f"Unknown response type: {response_type}")
            
    except Exception as e:
        print(f"Error in iteration: {e}")
        import traceback
        traceback.print_exc()
        iteration_response.append(f"Iteration error: {str(e)}")
        return await handle_error("ITERATION_ERROR", str(e))

async def main():
    global last_response, iteration, iteration_response
    reset_state()
    print("Starting main execution...")
    
    try:
        # Get user query
        # Find the ASCII values of characters in INDIA and then return sum of exponentials of those values. 
        query = input("Please enter your query: ")
        print("\nProcessing your query...")
        
        # Initialize environment
        client = initialize_environment()
        
        # Create MCP connection
        print("Establishing connection to MCP server...")
        server_params = StdioServerParameters(
            command="python",
            args=["assignment4/server.py"]
        )
        
        async with stdio_client(server_params) as (read, write):
            print("Connection established, creating session...")
            async with ClientSession(read, write) as session:
                print("Session created, initializing...")
                await session.initialize()
                
                # Get and process tools
                tools = await get_available_tools(session)
                tools_description = format_tool_descriptions(tools)
                system_prompt = create_system_prompt(tools_description)

                print(system_prompt)
                
                # Main iteration loop
                while iteration < max_iterations:
                    if last_response is None:
                        current_query = query
                    else:
                        current_query = query + "\n\n" + " ".join(iteration_response)
                        current_query = current_query + "  What should I do next?"
                    
                    # Run iteration
                    should_stop = await run_iteration(session, tools, current_query, system_prompt, client)
                    if should_stop:
                        break
                    
                    iteration += 1
                    
                    # Wait for user input before next iteration
                    # if iteration < max_iterations:
                    #     input("\nPress Enter to continue to next iteration...")
    
    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        reset_state()

if __name__ == "__main__":
    asyncio.run(main())
