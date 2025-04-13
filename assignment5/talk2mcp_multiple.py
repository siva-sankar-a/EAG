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
servers = {
    'math': {
        'command': 'python',
        'args': ['assignment4/server.py'],
        'session': None,
        'tools': []
    },
    'gmail': {
        'command': 'python',
        'args': ['assignment4/gmail_server.py', '--creds-file-path', os.getenv("CREDS_FILE_PATH"), '--token-path', os.getenv("TOKEN_PATH")],
        'session': None,
        'tools': []
    }
}

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

def format_tool_descriptions(tools_list):
    """Format tool information into readable descriptions"""
    tools_description = []
    tool_index = 0
    
    for server_name, server_data in tools_list.items():
        tools = server_data['tools']
        for tool in tools:
            try:
                params = tool.inputSchema
                desc = getattr(tool, 'description', 'No description available')
                name = getattr(tool, 'name', f'tool_{tool_index}')
                
                if 'properties' in params:
                    param_details = []
                    for param_name, param_info in params['properties'].items():
                        param_type = param_info.get('type', 'unknown')
                        param_details.append(f"{param_name}: {param_type}")
                    params_str = ', '.join(param_details)
                else:
                    params_str = 'no parameters'

                tool_desc = f"{tool_index+1}. {name}({params_str}) - {desc} [Server: {server_name}]"
                tools_description.append(tool_desc)
                print(f"Added description for tool: {tool_desc}")
            except Exception as e:
                print(f"Error processing tool {tool_index}: {e}")
                tools_description.append(f"{tool_index+1}. Error processing tool")
            tool_index += 1
    
    return "\n".join(tools_description)

def create_system_prompt(tools_description):
    """Generate the system prompt with tool descriptions"""
    return f"""You are a math and email agent solving problems in iterations. You have access to various mathematical tools and email tools.

You also have access to a paint application which is used mainly for displaying results.
You can use the paint application to draw rectangles and add text.

If you want to display anything in paint use the following steps:-
    1. You should collect the text to be displayed and use the add_text_in_paint tool to display the text.
    2. You should use the draw_rectangle tool to draw a rectangle around the text.

When you want to send a mail use the following steps:-
    1. You should come up with a subject and message for the mail.
    2. You should use the send-email tool to send the mail.
    
Available tools:
{tools_description}

You must respond with EXACTLY ONE line in one of these formats (no additional text):
1. For function calls:
   FUNCTION_CALL: function_name|param1|param2|...
   
2. For final answers:
   FINAL_ANSWER: [number]

Important:
- When a function returns multiple values, you need to process all of them
- Only give FINAL_ANSWER when you have completed all necessary calculations
- Do not repeat function calls with the same parameters

Examples:
- FUNCTION_CALL: add|5|3
- FUNCTION_CALL: strings_to_chars_to_int|INDIA
- FUNCTION_CALL: draw_rectangle|540|700|1080|1440
- FUNCTION_CALL: add_text_in_paint|Hello
- FUNCTION_CALL: send_mail|siva@gmail.com|Hello|This is a test mail
- FINAL_ANSWER: [42]

DO NOT include any explanations or additional text.
Your entire response should be a single line starting with either FUNCTION_CALL: or FINAL_ANSWER:"""

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

def parse_function_call(response_text):
    """Parse function call string into components"""
    _, function_info = response_text.split(":", 1)
    parts = [p.strip() for p in function_info.split("|")]
    return parts[0], parts[1:]

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

async def execute_tool(server_name, func_name, arguments):
    """Execute tool on a specific server"""
    server_data = servers[server_name]
    server_params = StdioServerParameters(
        command=server_data['command'],
        args=server_data['args']
    )
    
    print(f"Executing {func_name} on {server_name} server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            result = await session.call_tool(func_name, arguments=arguments)
            if hasattr(result, 'content'):
                if isinstance(result.content, list):
                    return [item.text if hasattr(item, 'text') else str(item) for item in result.content]
                return str(result.content)
            return str(result)

async def get_server_tools(server_name):
    """Get tools from a specific server"""
    server_data = servers[server_name]
    server_params = StdioServerParameters(
        command=server_data['command'],
        args=server_data['args']
    )
    
    print(f"Connecting to {server_name} server...")
    async with stdio_client(server_params) as (read, write):
        print(f"Connection established to {server_name}, creating session...")
        async with ClientSession(read, write) as session:
            print(f"Session created for {server_name}, initializing...")
            await session.initialize()
            
            # Get and process tools
            tools = await get_available_tools(session)
            print(f"Successfully retrieved {len(tools)} tools from {server_name} server")
            return tools

def format_tool_result(result):
    """Format tool execution results"""
    if isinstance(result, list):
        return f"[{', '.join(result)}]"
    return str(result)

async def handle_final_answer(response_text):
    """Handle final answer"""
    # Extract the number from FINAL_ANSWER: [number]
    if isinstance(response_text, str):
        if response_text.startswith("FINAL_ANSWER:"):
            # Extract the number between square brackets
            match = re.search(r'\[(.*?)\]', response_text)
            if match:
                number = match.group(1)
                print(f"Final answer: {number}")
            else:
                print("No number found in FINAL_ANSWER")
        else:
            print("Invalid FINAL_ANSWER format")
    else:
        print(response_text.content[0].text)

def find_tool_server(func_name):
    """Find which server contains the requested tool"""
    for server_name, server_data in servers.items():
        for tool in server_data['tools']:
            if tool.name == func_name:
                return server_name
    return None

async def run_iteration(tools_list, current_query, system_prompt, client):
    """Handle single iteration of the problem-solving process"""
    global iteration, last_response, iteration_response
    
    print(f"\n--- Iteration {iteration + 1} ---")
    prompt = f"{system_prompt}\n\nQuery: {current_query}"
    
    try:
        response = await generate_with_timeout(client, prompt)
        response_text = response.text.strip()
        print(f"LLM Response: {response_text}")
        
        # Find the FUNCTION_CALL line in the response
        for line in response_text.split('\n'):
            line = line.strip()
            if line.startswith("FUNCTION_CALL:"):
                response_text = line
                break
        
        if response_text.startswith("FUNCTION_CALL:"):
            func_name, params = parse_function_call(response_text)
            
            # Find the server that has this tool
            server_name = find_tool_server(func_name)
            if not server_name:
                raise ValueError(f"Unknown tool: {func_name}")
            
            # Find the matching tool
            tool = next((t for t in tools_list[server_name]['tools'] if t.name == func_name), None)
            if not tool:
                raise ValueError(f"Tool {func_name} not found in server {server_name}")
            
            # Execute the tool
            arguments = prepare_tool_arguments(tool, params)
            result = await execute_tool(server_name, func_name, arguments)
            result_str = format_tool_result(result)
            
            # Update iteration state
            iteration_response.append(
                f"In the {iteration + 1} iteration you called {func_name} with {arguments} parameters, "
                f"and the function returned {result_str}."
            )
            last_response = result_str
            return False  # Continue iterations
            
        elif response_text.startswith("FINAL_ANSWER:"):
            await handle_final_answer(response_text)
            return True  # Stop iterations
            
    except Exception as e:
        print(f"Error in iteration: {e}")
        import traceback
        traceback.print_exc()
        iteration_response.append(f"Error in iteration {iteration + 1}: {str(e)}")
        return True  # Stop iterations on error

async def main():
    global last_response, iteration, iteration_response
    reset_state()
    print("Starting main execution...")
    
    try:
        # Get user query
        query = input("Please enter your query: ")
        print("\nProcessing your query...")
        
        # Initialize environment
        client = initialize_environment()
        
        # Get tools from all servers
        print("Fetching tools from all servers...")
        for server_name in servers:
            print(f"Getting tools from {server_name} server...")
            tools = await get_server_tools(server_name)
            servers[server_name]['tools'] = tools
        
        # Format all tools from both servers
        tools_description = format_tool_descriptions(servers)
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
            should_stop = await run_iteration(
                servers,
                current_query,
                system_prompt,
                client
            )
            if should_stop:
                break
            
            iteration += 1
    
    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        reset_state()

if __name__ == "__main__":
    asyncio.run(main()) 