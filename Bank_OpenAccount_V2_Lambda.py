import json
import os
import time
import boto3
import uuid
import logging
from decimal import Decimal

from boto3 import session


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
#     slots = try_ex(lambda: get_slots(intent_request))
#     if slots is not None and slotName in slots and slots[slotName] is not None:
#         return slots[slotName]['value']['interpretedValue']
#     else:
#         return None 


def get_session_attributes(intent_request):
    sessionState = intent_request['sessionState']
    if 'sessionAttributes' in sessionState:
        return sessionState['sessionAttributes']
    
    return {}



def close(intent_name, session_attributes, fulfillment_state, message):
    '''Closes/Ends current Lex session with customer'''

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
                'confirmationState': 'Confirmed',
                'name': intent_name,
                'state': fulfillment_state
            }
        }
    }

    return response
    


def elicit_intent(session_attributes, message):
    '''Informs Amazon Lex that the user is expected to respond with an utterance that includes an intent. '''
    
    return {
        'sessionState':{
            'dialogAction':{
                'type':'ElicitIntent'
            },
            'sessionAttributes': session_attributes
        },
        'messages': [message] if message != None else None
    }


def confirm_intent(session_attributes, intent_name, slots, message):
    '''Informs Amazon Lex that the user is expected to give a yes or no answer to confirm or deny the current intent'''
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


def elicit_slot(intent_name, slots, violated_slot, session_attributes, message):
    '''Re-prompts user to provide a slot value in the response'''
    return {
        'sessionState':{
            'sessionAttributes': session_attributes,
            'dialogAction':{
                'slotToElicit': violated_slot,
                'type':'ElicitSlot'
            },
            'intent':{
                'confirmationState': 'Denied',
                'name':intent_name,
                'slots':slots,
                'state':'InProgress'
            }
        },
        'messages': [message] if message != None else None
    }


def delegate(intent_name, slots, session_attributes):
    '''Directs Amazon Lex to choose the next course of action based on the bot configuration. '''
    return {
        'sessionState':{
            'sessionAttributes': session_attributes,
            'dialogAction':{
                'type':'Delegate'
            },
            'intent':{
                'name':intent_name,
                'slots': slots
            }
        }
    }


''' --- Validation Functions --- '''

def build_validation_result(is_valid, violated_slot, message_content):

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message':{
            'contentType':'PlainText',
            'content': message_content
        }
    }

def isValid_Word(word):

    if word:
        try:
            if word.isalpha(): 
                return True
        except ValueError:
            return False

    return False

def isValid_Pin(pin):
    
    if pin:
        try:
            pin = str(pin)
            logger.info(f'isValid PinNumber={pin}')
            if (pin.isnumeric() == 1) & (len(pin) == 4): 
                return True
        except ValueError:
            return False
    
    return False


def isValid_AccountType(accountType):

    account_types = ['checking', 'savings', 'checkings','saving']

    return accountType.lower() in account_types


def isValid_SSN(ssn):

    if ssn:
        try:
            ssn = str(ssn)
            if ssn.isnumeric() & (len(ssn) == 12):
                return True
        except ValueError:
            return False

    return False


def validate_account_information(slots, session_attributes):

    #Get slots
    firstName = try_ex(lambda: session_attributes['FirstName'])
    lastName = try_ex(lambda: slots['LastName'])
    accountType = try_ex(lambda: slots['accountType'])
    pin = try_ex(lambda: slots['pin'])
    ssn = try_ex(lambda: slots['SSN'])

    logger.info(f'accountType={accountType}, firstName={firstName}, pin={pin}')

    if accountType and not isValid_AccountType(accountType['value']['interpretedValue']):
        return build_validation_result(
            False,
            'accountType',
            f'Sorry {firstName}, I did not understand. Would you like to open a Checking account or a Savings account?'
        )
    
    if ssn and not isValid_SSN(ssn['value']['interpretedValue']):
        return build_validation_result(
            False,
            'SSN',
            f'Sorry {firstName}, I did not understand. Could you please repeat your twelve digit Social Security Number.'
        )

    if lastName and not isValid_Word(lastName['value']['interpretedValue']):
        return build_validation_result(
            False,
            'lastName',
            f"<speak> Sorry {firstName}, I did not understand, May you repeat your last name to me once more, it would help if you could spell it out for me, like <say-as interpret-as='spell-out' Hello </say-as> </speak>"
        )

    if pin:
        logger.info(f'pin={pin} and user_pin={user_pin}')
        if not isValid_Pin(pin['value']['interpretedValue']):
            return build_validation_result(
                False,
                'pin',
                f'Sorry {firstName}, this is not a valid pin. Please tell us the four digit pin number you would like to use for your account.'
            )
    
    return {'isValid':True}


    
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

def getValid_AccountNumber():

    table_name = tbl_name

    accountNumber = Decimal(str(uuid.uuid4().int)[:12])

    table = dyn_resource.Table(table_name)

    try:
        response = table.get_item(Key={
            'AccountNumber': Decimal(accountNumber)
        })['Item']
    except KeyError:
        return accountNumber

    return getValid_AccountNumber()


def write_item_dynamodb(items):
    '''Inserts element into DynamoDB'''
    from botocore.exceptions import ClientError

    table_name = tbl_name

    table = dyn_resource.Table(table_name)

    try:
        response = table.put_item(Item=items)
    except ClientError as err:
        if err.response['Error']['Code'] == 'InternalError':
            logger.info('Error Message: {}'.format(err.response['Error']['Message']))
        else:
            raise err

    return True


def process(sessionAttributes, slots):

    response = {
        'AccountNumber': { "N": sessionAttributes['accountNumber']},
        'Pin': { 'N': slots['pin']},
        'AccountType':{'S': slots['accountType']},
        'FirstName': {'S': sessionAttributes['firstName']},
        'LastName': {'S': slots['lastName']},
        'SSN': {'N': slots['SSN']}
    }

    return response


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

    if source == 'DialogCodeHook':
        #Validate any slots which have been specified If any invalid, re-elicit for the slot value.
        validation_result = validate_account_information(slots, session_attributes)
        logger.info('validation_result is {} for the slot={}'.format(validation_result['isValid'],slots))
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None 
            logger.debug(f'slots={slots}')
            logger.info('violatedSlot={}, message={}'.format(validation_result['violatedSlot'], validation_result['message']))
            if validation_result['violatedSlot'] == 'LastName':
                return {
        'sessionState':{
            'sessionAttributes': session_attributes,
            'dialogAction':{
                'slotElicitationStyle': 'SpellByLetter',
                'slotToElicit': 'LastName',
                'type':'ElicitSlot',

            },
            'intent':{
                'confirmationState': 'Denied',
                'name':intent_name,
                'slots':slots,
                'state':'InProgress'
            }
        },
        'messages': validation_result['message']
    }
            else:
                return elicit_slot(
                    intent_name,
                    slots,
                    validation_result['violatedSlot'],
                    session_attributes,
                    validation_result['message']
                )
        
        return delegate(intent_name,intent_request['sessionState']['intent']['slots'] ,session_attributes)


    session_attributes['accountNumber'] = getValid_AccountNumber()

    firstName = session_attributes['FirstName']
    lastName = slots['LastName']
    accountType = slots['AccountType']

    #Process information into dictionary for DynamoDB entry format
    db_entry = process(session_attributes, slots)

    #Write processed informtion into DynamoDB
    if write_item_dynamodb(db_entry):

        logger.info(f'firstName={firstName}, lastName={lastName}, accountType={accountType}')
        logger.info(f'Info to be put into Database: {db_entry}')

        out1 =  f'Awesome! We have finished processing your information and your new {accountType} is now open and ready for use.'
        out2 = f'You can log in with username {lastName} and the password is the last four of your social. You can change this in settings.'
        out3 = f'Thank you {firstName} for choosing to open an account with Example Bank. We appreciate your business. '
        out4= f'Please stay on the line if you would like to take part in a customer experience survey.'
        output = out1+out2+out3+out4
        fulfillment_state = 'Fulfilled'

        message = {'contentType':'PlainText', 'content':output}
        
        return close(intent_name, session_attributes, fulfillment_state, message)
    
    else:
        raise Exception('Error writing into DynamoDB')



''' --- INTENTS --- '''


def dispatch(intent_request):

    intent_name = intent_request['sessionState']['intent']['name']

    #Dispatch to bot's intent handlers
    if intent_name == 'OpenAccount':
        return OpenAccount(intent_request)
    
    raise Exception('Intent with name ' + intent_name + ' not supported')




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



