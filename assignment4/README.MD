# Assignment 4 - MCP Servers and Clients

## Server Files

### server.py
A calculator server that provides various mathematical operations including:
- Basic arithmetic (add, subtract, multiply, divide)
- Advanced math (power, square root, cube root, factorial, log)
- Trigonometric functions (sin, cos, tan)
- Image processing (create thumbnail)
- Paint application integration (draw rectangle, add text)
- Code review and debugging capabilities

### gmail_server.py
A Gmail integration server that provides email management capabilities:
- Send emails
- Read emails
- Get unread emails
- Mark emails as read
- Trash emails
- Uses Google OAuth2 for authentication

## Client Files

### talk2mcp-2.py
A single-server client implementation that:
- Connects to one MCP server
- Uses Gemini AI for processing
- Handles tool execution and responses
- Manages conversation state
- Provides timeout handling for AI responses

Key Features:
- Iterative problem-solving approach
- Structured response format (FUNCTION_CALL or FINAL_ANSWER)
- Paint application integration for visual output
- Tool description formatting and management

Important Code Snippets:
```python
# System prompt creation with tool descriptions
def create_system_prompt(tools_description):
    return f"""You are a math agent solving problems in iterations. You have access to various mathematical tools.
You also have access to a paint application.
You can use the paint application to draw rectangles and add text.

Available tools:
{tools_description}

You must respond with EXACTLY ONE line in one of these formats (no additional text):
1. For function calls:
   FUNCTION_CALL: function_name|param1|param2|...
2. For final answers:
   FINAL_ANSWER: [number]"""
```

### talk2mcp_multiple.py
An enhanced client that can connect to multiple servers simultaneously:
- Supports both calculator and Gmail servers
- Manages multiple server connections
- Routes tool calls to appropriate servers
- Provides unified interface for interacting with multiple services
- Handles server-specific authentication and configurations

Key Features:
- Multi-server architecture
- Server-specific tool routing
- Combined email and math capabilities
- Enhanced error handling and state management

Important Code Snippets:
```python
# Server configuration
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

# Tool server routing
def find_tool_server(func_name):
    """Find which server contains the requested tool"""
    for server_name, server_data in servers.items():
        for tool in server_data['tools']:
            if tool.name == func_name:
                return server_name
    return None
```
