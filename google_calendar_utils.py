import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google_calendar():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                pass

        if not creds or not creds.valid:
            if not os.path.exists('credentials.json'):
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

            with open('token.json', 'w') as token:
                token.write(creds.to_json())

    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Failed to build service: {e}")
        return None

def fetch_google_calendar_events(service, max_results=20):
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    try:
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime').execute()
        events = events_result.get('items', [])
        return events
    except Exception as e:
        print(f"Error fetching events: {e}")
        return []

def create_google_calendar_event(service, titulo, data_hora):
    try:
        # Assuming data_hora is a string like "2024-05-20 10:00"
        start_time = datetime.datetime.strptime(data_hora, "%Y-%m-%d %H:%M")
        end_time = start_time + datetime.timedelta(hours=1) # Default 1 hour duration

        event = {
            'summary': titulo,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Sao_Paulo',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Sao_Paulo',
            },
        }

        event = service.events().insert(calendarId='primary', body=event).execute()
        return event
    except Exception as e:
        print(f"Error creating event: {e}")
        return None
