from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import plotly.express as px
import pandas as pd
import json
from pydantic import BaseModel
from google import genai
import os
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import numpy as np
from datetime import datetime, timedelta
import logging
from rich.logging import RichHandler
import time
from carpark_utils import get_carpark_status, format_carpark_status, get_carpark_history
from tabulate import tabulate

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)

# Suppress logs from other libraries
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("geopy").setLevel(logging.WARNING)
logging.getLogger("pandas").setLevel(logging.WARNING)
logging.getLogger("plotly").setLevel(logging.WARNING)

# Only show logs from our server
logger = logging.getLogger("parking_assistant")
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Configure Google AI
GOOGLE_API_KEY = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=GOOGLE_API_KEY)

app = FastAPI()

# Enable CORS for the Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["chrome-extension://*"],  # Allows all Chrome extensions
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Query(BaseModel):
    query: str = ""

class SuburbQuery(BaseModel):
    suburb: str

df_stations = pd.read_csv('assignment3/stations.csv')
df_stations['Coordinates'] = df_stations['Coordinates'].apply(lambda x: tuple(map(float, x.split())))

def get_coordinates_from_suburb(suburb: str):
    geolocator = Nominatim(user_agent="my_agent")
    try:
        location = geolocator.geocode(f"{suburb}, Sydney, Australia")
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        print(f"Error geocoding suburb: {e}")
        return None

def get_closest_suburb(suburb: str):
    """Returns the closest suburb from our station list"""
    suburb_coords = get_coordinates_from_suburb(suburb)
    if not suburb_coords:
        return None
    
    # Calculate distances
    distances = df_stations['Coordinates'].apply(lambda x: geodesic(suburb_coords, x).kilometers)
    closest_idx = distances.idxmin()
    
    return {
        'suburb': df_stations.loc[closest_idx, 'Name'].split(' Station')[0],
        'distance': round(distances[closest_idx], 2)
    }

def find_closest_station(suburb: str):
    """Finds the closest station to a given suburb"""
    suburb_coords = get_coordinates_from_suburb(suburb)
    if not suburb_coords:
        return None

    # Calculate distances
    distances = df_stations['Coordinates'].apply(lambda x: geodesic(suburb_coords, x).kilometers)
    closest_idx = distances.idxmin()
    
    closest_station = {
        'name': df_stations.loc[closest_idx, 'Name'],
        'distance': round(distances[closest_idx], 2),
        'spots': df_stations.loc[closest_idx, 'Number of spots'],
        'update_frequency': df_stations.loc[closest_idx, 'Update Frequency']
    }
    
    return closest_station

def get_occupancy_of_station(station_name: str):
    """Gets current occupancy of a station"""
    try:
        # Get station ID from df_stations
        station = df_stations[df_stations['Name'] == station_name]
        if station.empty:
            return None
            
        station_id = str(station.iloc[0]['ID'])
        event_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get car park status
        status = get_carpark_status(station_id, event_date)
        return status['total_occupancy'] / status['total_spots'] if status['total_spots'] > 0 else 0
    except Exception as e:
        logger.error(f"Error getting occupancy: {e}")
        return None

def get_total_spots_of_station(station_name: str):
    """Gets total number of spots at a station"""
    try:
        station = df_stations[df_stations['Name'] == station_name]
        if station.empty:
            return None
            
        station_id = str(station.iloc[0]['ID'])
        event_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get car park status
        status = get_carpark_status(station_id, event_date)
        return status['total_spots']
    except Exception as e:
        logger.error(f"Error getting total spots: {e}")
        return None

def get_parking_history_data_of_the_station(station_name: str, event_date: str = datetime.now().strftime("%Y-%m-%d")):
    """Gets historical parking data for a station"""
    try:
        # First try to find exact match
        station = df_stations[df_stations['Name'] == station_name]
        
        # If no exact match, find closest station
        if station.empty:
            # Get coordinates of the requested station
            station_coords = get_coordinates_from_suburb(station_name)
            if not station_coords:
                logger.error(f"Could not find coordinates for station: {station_name}")
                return None
                
            # Calculate distances to all stations
            distances = df_stations['Coordinates'].apply(lambda x: geodesic(station_coords, x).kilometers)
            closest_idx = distances.idxmin()
            
            # Get the closest station
            station = df_stations.iloc[[closest_idx]]
            logger.info(f"Using closest station: {station['Name'].iloc[0]} (distance: {round(distances[closest_idx], 2)}km)")
            
        station_id = str(station.iloc[0]['ID'])
        
        # Get historical data from API
        history_data = get_carpark_history(station_id, event_date)
        if not history_data:
            logger.error(f"No historical data available for station: {station_name}")
            return None
            
        # Process the data for visualization
        records = []
        for record in history_data:
            timestamp = datetime.strptime(record['MessageDate'], '%Y-%m-%dT%H:%M:%S')
            for zone in record['zones']:
                zone_name = f"Zone {zone['zone_id']}"
                total_spots = int(zone['spots'])
                occupancy = int(zone['occupancy']['total'])
                availability = total_spots - occupancy
                
                records.append({
                    'Time': timestamp,
                    'Zone': zone_name,
                    'Total Spots': total_spots,
                    'Occupancy': occupancy,
                    'Availability': availability,
                    'Occupancy Rate': occupancy / total_spots if total_spots > 0 else 0
                })
        
        # Create DataFrame with historical data
        df = pd.DataFrame(records)
        return df
    except Exception as e:
        logger.error(f"Error getting parking history: {e}")
        return None

def get_carpark_status_for_station(station_name: str):
    """Gets detailed car park status for a station"""
    try:
        station = df_stations[df_stations['Name'] == station_name]
        if station.empty:
            return None
            
        station_id = str(station.iloc[0]['ID'])
        event_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get car park status
        status = get_carpark_status(station_id, event_date)
        return status
    except Exception as e:
        logger.error(f"Error getting car park status: {e}")
        return None

def function_caller(func_name: str, params: list):
    """Calls the appropriate function based on the function name"""
    if func_name == "get_closest_suburb":
        return get_closest_suburb(*params)
    elif func_name == "find_closest_station":
        return find_closest_station(*params)
    elif func_name == "get_occupancy_of_station":
        return get_occupancy_of_station(*params)
    elif func_name == "get_total_spots_of_station":
        return get_total_spots_of_station(*params)
    elif func_name == "get_parking_history_data_of_the_station":
        return get_parking_history_data_of_the_station(*params)
    elif func_name == "get_carpark_status_for_station":
        return get_carpark_status_for_station(*params)
    else:
        return f"Unknown function: {func_name}"

@app.post("/parking_query")
async def parking_query(query: Query):
    max_iterations = 5
    last_response = None
    iteration = 0
    iteration_response = []
    start_time = time.time()
    graphical_data = None  # Track graphical data

    logger.info(f"\n[bold]Starting query: {query.query}[/bold]")

    system_prompt = """You are a parking information agent solving queries in iterations. Respond with EXACTLY ONE of these formats:
    1. FUNCTION_CALL: python_function_name|input
    2. FINAL_ANSWER: [detailed response]

    If there are multiple inputs split them with a comma.

    where python_function_name is one of the following:
    1. find_closest_station(suburb) - Finds the closest station to a given suburb
    2. get_occupancy_of_station(station_name) - Gets current occupancy of a station (returns value between 0 and 1)
    3. get_total_spots_of_station(station_name) - Gets total number of spots at a station
    5. get_parking_history_data_of_the_station(station_name, event_date) - Gets historical parking data for a station, event_date is The event date you wish to get data from. Format: YYYY-MM-DD ex: 2019-11-14
    6. get_carpark_status_for_station(station_name) - Gets detailed car park status including availability, zones, and location

    If any function fails regarding the station name try using the closest station approach.
    Do not show any tables in the output just get some aggregate stats.

    DO NOT include multiple responses. Give ONE response at a time."""

    while iteration < max_iterations:
        iteration_start_time = time.time()
        logger.info(f"\n[bold]Iteration {iteration + 1}/{max_iterations}[/bold]")
        
        if last_response is None:
            current_query = query.query
        else:
            current_query = query.query + "\n\n" + " ".join(iteration_response)
            current_query = current_query + "  What should I do next?"

        # Get model's response
        prompt = f"{system_prompt}\n\nQuery: {current_query}"
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        response_text = response.text.strip()
        
        if response_text.startswith("FUNCTION_CALL:"):
            _, function_info = response_text.split(":", 1)
            func_name, params = [x.strip() for x in function_info.split("|", 1)]
            params = params.split(",")
            logger.info(f"[bold]Executing:[/bold] {func_name}({params})")
            
            iteration_result = function_caller(func_name, params)
            
            # Create visualization if we have parking history data
            if func_name == "get_parking_history_data_of_the_station":
                df = iteration_result
                if iteration_result is not None:
                    # Create a figure with secondary y-axis
                    fig = px.line(df, 
                                x='Time', 
                                y=['Occupancy', 'Availability'],
                                color='Zone',
                                title='Parking Status by Zone Over Time',
                                labels={
                                    'Time': 'Time',
                                    'value': 'Number of Spots',
                                    'variable': 'Status',
                                    'Zone': 'Zone'
                                })
                    
                    # Update layout for better readability
                    fig.update_layout(
                        hovermode='x unified',
                        legend_title='Status by Zone',
                        yaxis_title='Number of Spots',
                        xaxis_title='Time'
                    )
                    
                    # Convert the figure to JSON and ensure it matches the expected structure
                    graph_json = json.loads(fig.to_json())
                    graphical_data = {
                        "data": graph_json["data"],
                        "layout": graph_json["layout"]
                    }

                    iteration_result = tabulate(df.describe(), headers='keys', tablefmt='grid')
                else:
                    iteration_result = "I couldn't find the parking history data for the station."

        elif response_text.startswith("FINAL_ANSWER:"):
            final_answer = response_text.replace("FINAL_ANSWER:", "").strip()
            execution_time = time.time() - start_time
            logger.info(f"\n[bold]Query completed in {execution_time:.2f}s[/bold]")
            return {
                "text_response": final_answer,
                "graphical_data": graphical_data
            }

        iteration_response.append(f"In the {iteration + 1} iteration you called {func_name} with {params} parameters, and the function returned {iteration_result}.")
        last_response = iteration_result
        
        iteration += 1

    execution_time = time.time() - start_time
    logger.info(f"\n[bold]Query terminated after {execution_time:.2f}s[/bold]")
    return {
        "text_response": "I couldn't complete the query in the maximum number of iterations.",
        "graphical_data": graphical_data
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)