import json
import os
import time
import boto3
import logging
import uuid 
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


def build_validation_result(is_valid, violated_slot, message_content):

    return {
        'isValid': is_valid,
        'violatedSlot': violated_slot,
        'message':{
            'contentType':'PlainText',
            'content': message_content
        }
    }



''' --- Validation Functions --- '''


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

def isValid_AccountNumber(accountNumber):

    if accountNumber is not None:
        try:
            accountNumber = str(accountNumber)
            logger.info(f'isValid AccountNumber={accountNumber}')
            if (len(accountNumber) == 12) & (accountNumber.isnumeric() == 1):
                return True
        except ValueError:
            return False
            
    return False


def isValid_AccountType(accountType):

    account_types = ['checking', 'savings', 'checkings','saving']

    return accountType.lower() in account_types



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


def validate_balance_information(slots):

    table_name = tbl_name 

    #Get slots
    accountType = try_ex(lambda: slots['accountType'])
    accountNumber = try_ex(lambda: slots['accountNumber'])
    pin = try_ex(lambda: slots['pin'])

    logger.info(f'accountType={accountType}, accountNumber={accountNumber}, pin={pin}')


    if accountType and not isValid_AccountType(accountType['value']['interpretedValue']):
        return build_validation_result(
            False,
            'accountType',
            'Sorry I did not understand. Would you like to get the account balance for your Checking account or your Savings account?'
        )
    
    if accountNumber:
        if not isValid_AccountNumber(accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry this is not a valid account number. Please enter your twelve digit {} account number'.format(accountType['value']['interpretedValue'])
            )
        if not validate_account_dynamodb(table_name, accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry but the account number {} does not exist in our database. Please enter your twelve digit account number.'.format(accountNumber['value']['interpretedValue'])
            )

##TODO: Add a counter (perhaps to sessionAttributes) to put a cap on retries for Pin Number.  
    if pin:
        user_pin = pin['value']['interpretedValue']
        logger.info(f'pin={pin} and user_pin={user_pin}')
        if not isValid_Pin(user_pin):
            return build_validation_result(
                False,
                'pin',
                'Sorry this is not a valid pin. Please enter your four digit pin number.'
            )
        if Decimal(user_pin) != get_item_dynamodb(accountNumber['value']['interpretedValue'], 'Pin'):
            return build_validation_result(
                False,
                'pin',
                'The pin number entered is incorrect. Please enter your four digit pin number.'
            )
    
    return {'isValid':True}

def validate_followup_information(slots):
    
    
    table_name = tbl_name 

    #Get slots
    accountType = try_ex(lambda: slots['accountType'])
    firstName = try_ex(lambda: slots['firstName'])
    accountNumber = try_ex(lambda: slots['accountNumber'])
    pin = try_ex(lambda: slots['pin'])

    logger.info(f'accountType={accountType}, firstName={firstName}, accountNumber={accountNumber}, pin={pin}')

    if firstName:

        response = None

        if firstName and isValid_Word(firstName['value']['interpretedValue']):
            return build_validation_result(
                False,
                'firstName',
                f"<speak> Sorry, I did not understand, May you repeat your first name to me once more, it would help if you could spell it out for me, like <say-as interpret-as='spell-out' Hello </say-as> </speak>"
        )

        return response


    if accountType and not isValid_AccountType(accountType['value']['interpretedValue']):
        return build_validation_result(
            False,
            'accountType',
            'Sorry I did not understand. Would you like to get the account balance for your Checking account or your Savings account?'
        )
    
    if accountNumber:
        if not isValid_AccountNumber(accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry this is not a valid account number. Please enter your twelve digit {} account number'.format(accountType['value']['interpretedValue'])
            )
        if not validate_account_dynamodb(table_name, accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry but the account number {} does not exist in our database. Please enter your twelve digit account number.'.format(accountNumber['value']['interpretedValue'])
            )

##TODO: Add a counter (perhaps to sessionAttributes) to put a cap on retries for Pin Number.  
    if pin:
        user_pin = pin['value']['interpretedValue']
        logger.info(f'pin={pin} and user_pin={user_pin}')
        if not isValid_Pin(user_pin):
            return build_validation_result(
                False,
                'pin',
                'Sorry this is not a valid pin. Please enter your four digit pin number.'
            )
        if Decimal(user_pin) != get_item_dynamodb(table_name, accountNumber['value']['interpretedValue'], 'Pin'):
            return build_validation_result(
                False,
                'pin',
                'The pin number entered is incorrect. Please enter your four digit pin number.'
            )
    
    return {'isValid':True}



def validate_replace_card_information(slots):

    table_name = tbl_name 

    #Get slots
    accountNumber = try_ex(lambda: slots['accountNumber'])
    pin = try_ex(lambda: slots['pin'])
    firstName = try_ex(lambda: slots['firstName'])

    logger.info(f'accountNumber={accountNumber}, pin={pin}')

    if firstName and not isValid_Word(firstName['value']['interpretedValue']):
        return build_validation_result(
            False,
            'firstName',
            f"<speak>  I did not understand. May you repeat your first name to me once more, it would help if you could spell it out for me, like <say-as interpret-as='spell-out' Hello </say-as> </speak>"
        )

    
    if accountNumber:
        if not isValid_AccountNumber(accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry this is not a valid account number. Please enter your twelve digit bank account number'
            )

        if not validate_account_dynamodb(table_name, accountNumber['value']['interpretedValue']):
            return build_validation_result(
                False,
                'accountNumber',
                'Sorry but the account number {} does not exist in our database. Please enter your twelve digit account number.'.format(accountNumber['value']['interpretedValue'])
            )

    if pin:
        user_pin = pin['value']['interpretedValue']
        logger.info(f'pin={pin} and user_pin={user_pin}')
        if not isValid_Pin(user_pin):
            return build_validation_result(
                False,
                'pin',
                'Sorry this is not a valid pin. Please enter your four digit pin number.'
            )
        if Decimal(user_pin) != get_item_dynamodb(accountNumber['value']['interpretedValue'], 'Pin'):
            return build_validation_result(
                False,
                'pin',
                'The pin number entered is incorrect. Please enter your four digit pin number.'
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


def get_item_dynamodb(accountNumber, query_params):
    '''retrieves element from DynamoDB'''

    table_name = tbl_name

    table = dyn_resource.Table(table_name)
    
    if (accountNumber is None) | (query_params is None): return False

    try:
        response = table.get_item(Key={
            'AccountNumber': Decimal(accountNumber)
        })['Item']
    except KeyError:
        return False

    return response[query_params]

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




""" --- Functions that control the bot's behavior --- """

def Greeting(intent_request):
    pass

def CheckBalance(intent_request):

    table_name = tbl_name

    #Initialize required response parameters
    intent_name = intent_request['sessionState']['intent']['name']
    session_attributes = get_session_attributes(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    slots = get_slots(intent_request)

    logger.info(f'source={source}, slots={slots}, confirmation_status={confirmation_status}')


    if source == 'DialogCodeHook':
        # Valdiate any slots which have been specified. If any are invalid, re-elicit for their value.
        validation_result = validate_balance_information(slots)
        logger.info('validation_result is {} for the non-empty slots in {}'.format(validation_result['isValid'],slots))
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            logger.debug(f'slots={slots}')
            logger.info('violatedSlot={}, message={}'.format(validation_result['violatedSlot'], validation_result['message']))
            return elicit_slot(
                intent_name,
                slots,
                validation_result['violatedSlot'],
                session_attributes,
                validation_result['message']
            )
        
        return delegate(intent_name,intent_request['sessionState']['intent']['slots'] ,session_attributes)

    
    balance = get_item_dynamodb(slots['accountNumber']['value']['interpretedValue'], 'Account Balance')
    logger.info(f'balance={balance}')

    output1 = f'The balance on your account is ${balance:,.2f} dollars. '
    output2 = 'Thank you for banking with Example Bank. We appreciate your business. '
    output3= 'Please stay on the line if you would like to take our customer experience survey.'
    output = output1+output2+output3
    fulfillment_state = 'Fulfilled'

    message = {'contentType':'PlainText', 'content':output}
    
    return close(intent_name, session_attributes, fulfillment_state, message)


def FollowupCheckBalance(intent_request):
    
    table_name = tbl_name

    #Initialize required response parameters
    
    intent_name = intent_request['sessionState']['intent']['name']
    session_attributes = get_session_attributes(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    slots = get_slots(intent_request)

    logger.info(f'source={source}, slots={slots}, confirmation_status={confirmation_status}')

    logger.info(f'These are the session attributes: {session_attributes}')

    if source == 'DialogCodeHook':
        # Valdiate any slots which have been specified. If any are invalid, re-elicit for their value.
        validation_result = validate_followup_information(slots)
        logger.info('validation_result is {} for the non-empty slots in {}'.format(validation_result['isValid'],slots))
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            logger.debug(f'slots={slots}')
            logger.info('violatedSlot={}, message={}'.format(validation_result['violatedSlot'], validation_result['message']))
            if validation_result['violatedSlot'] == 'firstName':
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

    
    balance = get_item_dynamodb(slots['accountNumber']['value']['interpretedValue'], 'Account Balance')
    logger.info(f'balance={balance}')

    output1 = f'The balance on your account is ${balance:,.2f} dollars. '
    output2 = 'Thank you for banking with Example Bank. We appreciate your business. '
    output3= 'Please stay on the line if you would like to take our customer experience survey.'
    output = output1+output2+output3
    fulfillment_state = 'Fulfilled'

    message = {'contentType':'PlainText', 'content':output}
    
    return close(intent_name, session_attributes, fulfillment_state, message)



def ReplaceCard(intent_request):
    
    table_name = tbl_name

    #Initialize required response parameters
    intent_name = intent_request['sessionState']['intent']['name']
    session_attributes = get_session_attributes(intent_request)
    source = intent_request['invocationSource']
    confirmation_status = intent_request['sessionState']['intent']['confirmationState']
    slots = get_slots(intent_request)

    logger.info(f'source={source}, slots={slots}, confirmation_status={confirmation_status}')

    logger.info(f'These are the session attributes: {session_attributes}')

    if source == 'DialogCodeHook':
        # Valdiate any slots which have been specified. If any are invalid, re-elicit for their value.
        validation_result = validate_replace_card_information(slots)
        logger.info('validation_result is {} for the non-empty slots in {}'.format(validation_result['isValid'],slots))
        if not validation_result['isValid']:
            slots[validation_result['violatedSlot']] = None
            logger.debug(f'slots={slots}')
            logger.info('violatedSlot={}, message={}'.format(validation_result['violatedSlot'], validation_result['message']))
            if validation_result['violatedSlot'] == 'firstName':
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


    #Generate/Initalize Output values
    cardNumber = Decimal(str(uuid.uuid4().int)[:16]
    email_address = get_item_dynamodb(slots['accountNumber']['value']['interpretedValue'], 'Email Address')
    street_address = get_item_dynamodb(slots['acountNumber']['value']['interpretedValue'], 'Street Address')
    
    logger.info(f'cardNumber={cardNumber}, email address={email_address}, street_address={street_address}')

    out = f'An email has been sent to {email_address} containing your new debit card information. ' 
    out2 = f'Your new debit card ending in {cardNumber[-4:]} has been mailed out to {street_address}. '
    out3 = 'Please expect it to arrive within five to seven business days.'
    
    output = out+out2+out3
    fulfillment_state = 'Fulfilled'

    message = {'contentType':'PlainText', 'content':output}
    
    return close(intent_name, session_attributes, fulfillment_state, message)



''' --- INTENTS --- '''


def dispatch(intent_request):

    intent_name = intent_request['sessionState']['intent']['name']
    
    logger.info(f'intent_name={intent_name}')
    

    #Dispatch to bot's intent handlers
    if intent_name == 'CheckBalance':
        return CheckBalance(intent_request)

    elif intent_name == 'Greeting':
        return Greeting(intent_request)

    elif intent_name == 'FollowupCheckBalance':
       return FollowupCheckBalance(intent_request)

    elif intent_name == 'ReplaceCard':
        return ReplaceCard(intent_request)

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