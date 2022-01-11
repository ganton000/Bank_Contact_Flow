import json
import os
import time
import boto3
import logging
from decimal import Decimal


#Configure logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


#Initialize DynamoDB resource
dyn_resource = boto3.resource('dynamodb')
tbl_name = 'BankAccountsNew'



""" --- Generic functions used to simplify interaction with Amazon Lex --- """

def get_slots(intent_request):
    return intent_request['sessionState']['intent']['slots']

# def get_slot(intent_request, slotName):
#     slots = get_slots(intent_request)
#     if slots is not None and slotName in slots and slots[slotName] is not None:
#         return slots[slotName]['value']['interpretedValue']
#     else:
#         return None 

def get_session_attributes(intent_request):
    sessionState = intent_request['sessionState']
    if 'sessionAttributes' in sessionState:
        return sessionState['sessionAttributes']
    
    return {}

def elicit_slot(session_attributes, intent_name, slots, slot_to_elicit, message):
    return {
        'messages': [
            message
        ],
        'sessionState': {
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'ElicitSlot',            
                'slotToElicit': slot_to_elicit
            },
            'intent': {
                'name': intent_name,
                'slots': slots
            }
        }
    }


def confirm_intent(session_attributes, intent_name, slots, message):
    return {
        'messages': [
            message
        ],
        'sessionState': {
            'sessionAttributes': session_attributes,
            'dialogAction': {
                'type': 'ConfirmIntent'
            },
            'intent': {
                'name': intent_name,
                'slots': slots
            }
        }
    }


def close(session_attributes, intent_name, fulfillment_state, message):
    response = {
        'messages': [
            message
        ],
        'sessionState': {
            'dialogAction': {
                'type': 'Close'           
            },
            'sessionAttributes': session_attributes,
            'intent': {
                'name': intent_name,
                'state': fulfillment_state
            }
        }
    }

    return response


def delegate(session_attributes, intent_name, slots):
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'Delegate'           
            },
            'sessionAttributes': session_attributes,
            'intent': {
                'name': intent_name,
                'slots': slots
            }
        }
    }

''' --- Validation Functions --- '''

def build_validation_result():
    pass 




""" --- Helper Functions --- """


def try_ex(func):
    """
    Call passed in function in try block. If KeyError is encountered return None.
    This function is intended to be used to safely access dictionary.

    Note that this function would have negative impact on performance.
    """

    try:
        return func()
    except KeyError:
        return None


def write_item_dynamodb(table_name, items):
    '''Inserts element into DynamoDB'''

    from botocore.exceptions import ClientError

    table = dyn_resource.Table(table_name)

    try:
        response = table.put_item(Item=items)
    except ClientError as err:
        if err.response['Error']['Code'] == 'InternalError':
            logger.info('Error Message: {}'.format(err.response['Error']['Message']))
        else:
            raise err

    return True
    

def validate_account_dynamodb(table_name, accountNumber):
    '''Checks if account number exists in DynamoDB'''
    
    if accountNumber is None: return False

    table = dyn_resource.Table(table_name)

    try:
        response = table.get_item(Key={
            'AccountNumber': Decimal(accountNumber)
        })['Item']
    except KeyError:
        return False

    return True


def generate_account_number():

    import uuid

    #Generate unique 12-digit Account Number
    newAccountNumber = Decimal(str(uuid.uuid4().int)[:12])


    #Validation check for uniqueness/existence
    if validate_account_dynamodb(table_name, newAccountNumber):
        generate_account_number()
    
    return Decimal(newAccountNumber)


""" --- Functions that control the bot's behavior --- """

def OpenAccount(intent_request):

    #Set DynamoDB table name
    table_name = tbl_name

    #Initialize required response parameters
    intent_name = intent_request['sessionState']['intent']['name']
    session_attributes = get_session_attributes(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    slots = get_slots(intent_request)

    logger.info(f'source={source}, slots={slots}, confirmation_status={confirmation_status}')


    #Get slot values
    accountType = slots['accountType']
    


''' --- INTENTS --- '''


def dispatch(intent_request):

    intent_name = intent_request['sessionState']['intent']['name']

    #Dispatch to bot's intent handlers
    if intent_name == 'OpenAccount':
        return OpenAccount(intent_request)


''' --- MAIN handler --- '''


def lambda_handler(event, context):
    
    # By default, treat the user request as coming from the America/New_York time zone.
    os.environ['TZ'] = 'America/New_York'
    time.tzset()


    bot_name = event['bot']['name']
    userMessage = event['inputTranscript'] #string
    inputType = event['inputMode'] #DTMF | Speech | Text
    

    logger.info(f'event.bot.name={bot_name}, userMessage={userMessage}, inputType={inputType}')


    return dispatch(event)



