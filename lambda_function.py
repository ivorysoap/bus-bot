import os
import json
import requests
import datetime

OC_TRANSPO_APP_ID = os.environ['OC_TRANSPO_APP_ID']
OC_TRANSPO_API_KEY = os.environ['OC_TRANSPO_API_KEY']
OC_TRANSPO_BASE_URL = 'https://api.octranspo1.com'
SLACK_TOKEN = os.environ['SLACK_BOT_TOKEN']
BOT_USER_ID = 'U01ST0S5X5K'

STANDARD_MESSAGE_WORD_COUNT = 3

COMMANDS = {"summary": "Provides a summary of the routes that serve the given stop.  Example: @BusBot summary 4442", "trips": "Provides the next few trips serving the given stop.  Example:  @BusBot trips 4442"}

HELP_MESSAGE = '''
I'm BusBot.  You can ask me questions about bus stops and the routes that serve them.  Here are my commands:\n
{}\n
You can communicate with me by @-ing me in a channel, or by just DMing me.
'''

class MalformedCommandError(Exception):
    """Exception raised when a Slack command is malformed."""
    pass

def getRouteSummaryForStop(stopNumber: int, format: str = 'json'):
    url = OC_TRANSPO_BASE_URL + '/v2.0/GetRouteSummaryForStop'
    params = dict()
    params['appID'] = OC_TRANSPO_APP_ID
    params['apiKey'] = OC_TRANSPO_API_KEY
    params['stopNo'] = stopNumber
    params['format'] = format
    if format in ('json', 'xml'):
        return requests.get(url, params=params).json()
    elif format == 'nice':
        params = dict()
        

def getNextTripsForStop(stopNumber: int, routeNumber: int, format: str = 'json'):
    url = OC_TRANSPO_BASE_URL + '/v2.0/GetNextTripsForStop'
    params = dict()
    params['appID'] = OC_TRANSPO_APP_ID
    params['apiKey'] = OC_TRANSPO_API_KEY
    params['stopNo'] = stopNumber
    params['routeNumber'] = routeNumber
    params['format'] = format
    return requests.get(url, params=params).json()

def getNextTripsForStopAllRoutes(stopNumber: int, format: str = 'json'):
    url = OC_TRANSPO_BASE_URL + '/v2.0/GetNextTripsForStopAllRoutes'
    params = dict()
    params['appID'] = OC_TRANSPO_APP_ID
    params['apiKey'] = OC_TRANSPO_API_KEY
    params['stopNo'] = stopNumber
    params['format'] = format
    return requests.get(url, params=params).json()

def sendMessage(channel: str, blocks: list):
    url = 'https://slack.com/api/chat.postMessage'
    headers = {'Authorization': 'Bearer {}'.format(SLACK_TOKEN)}

    payload = dict()
    payload['channel'] = channel
    payload['blocks'] = json.dumps(blocks)

    return requests.post(url=url, params=payload, headers=headers)

def formatSummary(data: dict):
    #TODO Use separate sections rather than \n-separated strings to represent routes in the summary.
    header = {"type": "header", "text": {"type": "plain_text", "text": f"Routes serving stop {data['GetRouteSummaryForStopResult']['StopNo']} ({data['GetRouteSummaryForStopResult']['StopDescription']})"}}
    routes = ''
    for route in data['GetRouteSummaryForStopResult']['Routes']:
        routes += '\n:bus: ' + route['RouteNo'] + '  ' + route['RouteHeading']
    attachments = [ {"type": "mrkdwn", "text": routes} ]
    section = {"type": "section", "fields": attachments}

    payload = [header, section]
    return payload

def formatTrips(data: dict):
    if 'GetRouteSummaryForStopResult' in data:
        header =    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Next trips for stop {data['GetRouteSummaryForStopResult']['StopNo']} ({data['GetRouteSummaryForStopResult']['StopDescription']})"
                        }
                    }
        data = data['GetRouteSummaryForStopResult']
    elif 'GetNextTripsForStopResult' in data:
        header =    {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"Next trips for stop {data['GetNextTripsForStopResult']['StopNo']} ({data['GetRouteSummaryForStopResult']['StopDescription']})"
                    }
                }
        data = data['GetNextTripsForStopResult']

    divider = { "type": "divider" }

    tripsBody = [header, divider]

    # To handle the case where there's 1 route - API returns dict rather than list
    routes = [ route for route in data['Routes']['Route'] ] if type(data['Routes']['Route']) is list else [ data['Routes']['Route'] ]

    for route in routes:
        		
        routeHeader =   {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text":  f":light_rail: {route['RouteNo']} {route['RouteHeading']}" if int(route['RouteNo']) in (1,2) else f":bus: {route['RouteNo']} {route['RouteHeading']}",
                                "emoji": True
                            }
                        }
        tripsBody.append(routeHeader)

        # To handle the case where there's only 1 trip left - API returns dict rather than list
        #trips = [ trip for trip in route['Trips'] ] if 'Trip' in route['Trips'] and type(route['Trips']['Trip']) is list else [ route['Trips']['Trip'] ]
        #trips = route['Trips']['Trip'] if 'Trip' in route['Trips'] and type(route['Trips']['Trip']) is list else [ route['Trips'] ]
        trips = route['Trips'] if type(route['Trips']) is list else [ route['Trips'] ]

        for trip in trips:
            
            now = datetime.datetime.now()
            adjustmentMinutes = datetime.timedelta(minutes=int(trip['AdjustedScheduleTime']))
            arrivalTime = now + adjustmentMinutes  # Used to determine bus arrival time
            tripSection =   {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"— At *{arrivalTime.strftime('%H:%M')}* (in {trip['AdjustedScheduleTime']} minutes) to {trip['TripDestination']}"
                                }
                            }
            tripsBody.append(tripSection)
        
    timeSection = 	{"type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f":clock2: Data fetched at *{now.strftime('%H:%M')}*"
                            }
                        ]
                    }
    tripsBody.append(timeSection)

    return tripsBody


def formatRoutes(data: dict):
    pass


def lambda_handler(Event, Context):
    messageString = Event['event']['text']
    message = messageString.split(" ")
    channel = event['event']['channel']

    try:
        # Get command
        words = dict()
        if '<@' + BOT_USER_ID + '>' in message:
            # Bot was @-ed from a channel
            if len(message) < len(COMMANDS) + 1:
                raise MalformedCommandError("Received malformed Slack command: {}".format(messageString))
            words['command'] = message[1]
            words['stopNumber'] = message[2]
        else:
            # Bot was DM-ed
            if len(message) < len(COMMANDS):
                raise MalformedCommandError("Received malformed Slack command: {}".format(messageString))
            words['command'] = message[0]
            words['stopNumber'] = message[1]
            if len(message) == len(COMMANDS) + 1:
                words['routeNumber'] = message[2]

        if words['command'].lower() in COMMANDS:
            # Query OC Transpo API
            if words['command'].lower() == 'summary':
                response = getRouteSummaryForStop(int(words['stopNumber']))
                payload = formatSummary(response)
                sendMessage(channel, payload)




            elif words['command'].lower() == 'trips':
                if 'routeNumber' in words:
                    response = getNextTripsForStop(int(words['stopNumber']), int(words['routeNumber']))
                else:
                    response = getNextTripsForStopAllRoutes(int(words['stopNumber']))
                payload = formatTrips(response)
                retval = sendMessage(channel, payload)

            print("Done.  Slack response: {}".format(retval))

            
    
    except MalformedCommandError:
        pass





if __name__ == '__main__':
    #event = {'token': 'YmYrkxapuKx0vROcwFF8gUXt', 'team_id': 'T01SW62JCMR', 'api_app_id': 'A01SF9JQPM5', 'event': {'client_msg_id': '2d44cc24-2b1c-44c1-9b25-05f649df3f20', 'type': 'app_mention', 'text': '<@U01ST0S5X5K> summary 6532', 'user': 'U01SP6BH54N', 'ts': '1619386349.000400', 'team': 'T01SW62JCMR', 'blocks': [{'type': 'rich_text', 'block_id': 'nQG', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'user', 'user_id': 'U01ST0S5X5K'}, {'type': 'text', 'text': ' trips 3000'}]}]}], 'channel': 'C01TKPE4M96', 'event_ts': '1619386349.000400'}, 'type': 'event_callback', 'event_id': 'Ev01VD8FCYTV', 'event_time': 1619386349, 'authorizations': [{'enterprise_id': None, 'team_id': 'T01SW62JCMR', 'user_id': 'U01ST0S5X5K', 'is_bot': True, 'is_enterprise_install': False}], 'is_ext_shared_channel': False, 'event_context': '1-app_mention-T01SW62JCMR-C01TKPE4M96'}
    #event = {'token': 'YmYrkxapuKx0vROcwFF8gUXt', 'team_id': 'T01SW62JCMR', 'api_app_id': 'A01SF9JQPM5', 'event': {'client_msg_id': 'b80b6fd9-80dc-491e-828e-152db7c220ad', 'type': 'app_mention', 'text': '<@U01ST0S5X5K> trips 2546', 'user': 'U01SP6BH54N', 'ts': '1619492504.000800', 'team': 'T01SW62JCMR', 'blocks': [{'type': 'rich_text', 'block_id': 'Tma', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'user', 'user_id': 'U01ST0S5X5K'}, {'type': 'text', 'text': ' trips 2546'}]}]}], 'channel': 'C01T25V3FMJ', 'event_ts': '1619492504.000800'}, 'type': 'event_callback', 'event_id': 'Ev020A0Q3YTE', 'event_time': 1619492504, 'authorizations': [{'enterprise_id': None, 'team_id': 'T01SW62JCMR', 'user_id': 'U01ST0S5X5K', 'is_bot': True, 'is_enterprise_install': False}], 'is_ext_shared_channel': False, 'event_context': '1-app_mention-T01SW62JCMR-C01TKPE4M96'}
    event = {'token': 'YmYrkxapuKx0vROcwFF8gUXt', 'team_id': 'T01SW62JCMR', 'api_app_id': 'A01SF9JQPM5', 'event': {'client_msg_id': 'b80b6fd9-80dc-491e-828e-152db7c220ad', 'type': 'app_mention', 'text': '<@U01ST0S5X5K> trips 3010', 'user': 'U01SP6BH54N', 'ts': '1619492504.000800', 'team': 'T01SW62JCMR', 'blocks': [{'type': 'rich_text', 'block_id': 'Tma', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'user', 'user_id': 'U01ST0S5X5K'}, {'type': 'text', 'text': ' trips 3010'}]}]}], 'channel': 'C01T25V3FMJ', 'event_ts': '1619492504.000800'}, 'type': 'event_callback', 'event_id': 'Ev020A0Q3YTE', 'event_time': 1619492504, 'authorizations': [{'enterprise_id': None, 'team_id': 'T01SW62JCMR', 'user_id': 'U01ST0S5X5K', 'is_bot': True, 'is_enterprise_install': False}], 'is_ext_shared_channel': False, 'event_context': '1-app_mention-T01SW62JCMR-C01TKPE4M96'}
    #event = {'token': 'YmYrkxapuKx0vROcwFF8gUXt', 'team_id': 'T01SW62JCMR', 'api_app_id': 'A01SF9JQPM5', 'event': {'client_msg_id': 'b80b6fd9-80dc-491e-828e-152db7c220ad', 'type': 'app_mention', 'text': '<@U01ST0S5X5K> trips 4440', 'user': 'U01SP6BH54N', 'ts': '1619492504.000800', 'team': 'T01SW62JCMR', 'blocks': [{'type': 'rich_text', 'block_id': 'Tma', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'user', 'user_id': 'U01ST0S5X5K'}, {'type': 'text', 'text': ' trips 4440'}]}]}], 'channel': 'C01T25V3FMJ', 'event_ts': '1619492504.000800'}, 'type': 'event_callback', 'event_id': 'Ev020A0Q3YTE', 'event_time': 1619492504, 'authorizations': [{'enterprise_id': None, 'team_id': 'T01SW62JCMR', 'user_id': 'U01ST0S5X5K', 'is_bot': True, 'is_enterprise_install': False}], 'is_ext_shared_channel': False, 'event_context': '1-app_mention-T01SW62JCMR-C01TKPE4M96'}
    lambda_handler(event, None)