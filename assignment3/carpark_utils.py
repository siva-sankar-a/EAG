import pandas as pd
from typing import Dict, List, Optional
import requests
import os
from datetime import datetime

def get_carpark_history(facility_id: str, event_date: str) -> List[Dict]:
    """
    Fetch car park history data from the TfNSW API.
    
    Args:
        facility_id (str): The facility ID from df_stations
        event_date (str): Event date in YYYY-MM-DD format
        
    Returns:
        List[Dict]: List of car park history records
    """
    api_key = os.getenv('CAR_PARK_API')
    if not api_key:
        raise ValueError("CAR_PARK_API environment variable not set")
        
    url = f"https://api.transport.nsw.gov.au/v1/carpark/history"
    params = {
        "facility": facility_id,
        "eventdate": event_date
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"apikey {api_key}"
    }
    
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()

def calculate_carpark_stats(history_data: List[Dict]) -> Dict:
    """
    Calculate statistics for a car park from its history data.
    
    Args:
        history_data (List[Dict]): List of car park history records
        
    Returns:
        Dict: Dictionary containing total spots, availability, and total occupancy
    """
    if not history_data:
        return {
            "total_spots": 0,
            "current_availability": 0,
            "total_occupancy": 0,
            "is_full": False,
            "is_almost_full": False
        }
    
    # Get the latest record
    latest_record = history_data[-1]
    
    # Calculate total spots (sum of spots across all zones)
    total_spots = sum(int(zone["spots"]) for zone in latest_record["zones"])
    
    # Calculate total occupancy (sum of total occupancy across all zones)
    total_occupancy = sum(int(zone["occupancy"]["total"]) for zone in latest_record["zones"])
    
    # Calculate availability
    availability = total_spots - total_occupancy
    
    # Calculate status flags
    is_full = availability < 1
    is_almost_full = availability < (total_spots * 0.1)  # Less than 10% available
    
    return {
        "total_spots": total_spots,
        "current_availability": availability,
        "total_occupancy": total_occupancy,
        "is_full": is_full,
        "is_almost_full": is_almost_full,
        "last_updated": latest_record["MessageDate"]
    }

def get_carpark_status(facility_id: str, event_date: str) -> Dict:
    """
    Get the current status of a car park facility.
    
    Args:
        facility_id (str): The facility ID from df_stations
        event_date (str): Event date in YYYY-MM-DD format
        
    Returns:
        Dict: Dictionary containing car park status information
    """
    history_data = get_carpark_history(facility_id, event_date)
    stats = calculate_carpark_stats(history_data)
    
    # Add facility information
    if history_data:
        latest_record = history_data[-1]
        stats.update({
            "facility_name": latest_record["facility_name"],
            "location": latest_record["location"],
            "zones": latest_record["zones"]
        })
    
    return stats

def format_carpark_status(status: Dict) -> str:
    """
    Format car park status into a human-readable string.
    
    Args:
        status (Dict): Car park status dictionary
        
    Returns:
        str: Formatted status message
    """
    if status["is_full"]:
        return f"{status['facility_name']} is FULL"
    elif status["is_almost_full"]:
        return f"{status['facility_name']} is ALMOST FULL (~{status['current_availability']} spots available)"
    else:
        return f"{status['facility_name']}: ~{status['current_availability']} spots available out of {status['total_spots']}"

# Example usage:
if __name__ == "__main__":
    # Example facility ID and date
    facility_id = "30"
    event_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        status = get_carpark_status(facility_id, event_date)
        print(format_carpark_status(status))
    except Exception as e:
        print(f"Error fetching car park status: {e}") 