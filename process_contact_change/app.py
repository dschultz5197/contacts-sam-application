from __future__ import print_function
import logging
import inspect


def lambda_handler(event, context):
    cur_function = inspect.currentframe().f_code.co_name
    final_results = []
    for record in event['Records']:
        result = []
        if record['eventName'] == "INSERT":
            # process new records
            try:
                print('Processing new record for event id %s.' % str(record['eventID']))
                result.append(new_record_handler(record['dynamodb']['NewImage']))
            except KeyError as e:
                result.append(error_handler('KeyError', cur_function, e))
            except Exception as e:
                result.append(error_handler('Exception', cur_function, e))
        elif record['eventName'] == "MODIFY":
            # process modified records
            try:
                print('Processing modified record for event id %s.' % str(record['eventID']))
                handler_results = modified_record_handler(record['dynamodb']['OldImage'], record['dynamodb']['NewImage'])
                for handler_result in handler_results:
                    result.append(handler_result)
                # result.append(modified_record_handler(record['dynamodb']['OldImage'], record['dynamodb']['NewImage']))
            except KeyError as e:
                result.append(error_handler('KeyError', cur_function, e))
            except Exception as e:
                result.append(error_handler('Exception', cur_function, e))
        elif record['eventName'] == "REMOVE":
            # process removed records
            try:
                print('Processing removed record for event id %s.' % str(record['eventID']))
                result.append(removed_record_handler(record['dynamodb']['OldImage']))
            except KeyError as e:
                result.append(error_handler('KeyError', cur_function, e))
            except Exception as e:
                result.append(error_handler('Exception', cur_function, e))
        final_results.append({"eventID": record['eventID'], "results": result})
    print('Processed %s records.' % str(len(event['Records'])))
    stats = {'SuccessfulEvents': 0, 'SuccessfulMessagesSent': 0, 'EventErrors': 0, 'MessageErrors': 0}
    for result in final_results:
        errors = 0
        success = 0
        for message_result in result['results']:
            if message_result['result'] == 'success':
                success += 1
            else:
                errors += 1
        if errors == 0:
            stats['SuccessfulEvents'] += 1
        else:
            stats['EventErrors'] += 1
        stats['SuccessfulMessagesSent'] += success
        stats['MessageErrors'] += errors
    print('Final Stats: %s' % stats)


def error_handler(error_type, cur_function, error):
    print('Handling %s from %s: %s' % (error_type, cur_function, error))
    return {"function": cur_function, "result": error_type, "error": error}


def new_record_handler(new_image):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        primary_contact_field = get_primary_contact_field(new_image['primary_contact_method']['S'])
        name = name_builder(new_image)
        message = 'Dear %s,\n Thank you for signing up for our contact list with %s as your primary contact.' \
                  % (name, new_image['primary_contact_method']['S'])
        result = message_handler(new_image['primary_contact_method']['S'], new_image[primary_contact_field]['S'], message)
    except KeyError as e:
        result = error_handler('KeyError', cur_function, e)
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    return result


def removed_record_handler(old_image):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        primary_contact_field = get_primary_contact_field(old_image['primary_contact_method']['S'])
        # Need/want to incorporate name into message.
        name = name_builder(old_image)
        message = 'Dear %s,\n We\'re sorry to see you go. Your contact record has been removed.' % name
        result = message_handler(old_image['primary_contact_method']['S'], old_image[primary_contact_field]['S'], message)
    except KeyError as e:
        result = error_handler('KeyError', cur_function, e)
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    return result


def modified_record_handler(old_image, new_image):
    # Will need to determine what changed, and send appropriate messaging to the primary_contact_method.
    # If something with the primary_contact_method has changed (either the method or the contact value) then send to
    # both the current and old.
    cur_function = inspect.currentframe().f_code.co_name
    send_to = []
    result = []
    try:
        name = name_builder(new_image)
        old_name = name_builder(old_image)
        primary_contact_change = None
        other_change = None
        name_change = 'The name on your contact has been updated.\n' if old_name != name else None
        old_primary_contact_field = get_primary_contact_field(old_image['primary_contact_method']['S'])
        new_primary_contact_field = get_primary_contact_field(new_image['primary_contact_method']['S'])
        # check if primary contact method changed.
        if old_primary_contact_field != new_primary_contact_field:
            # If so, add both the old primary contact and the new primary contact to the send to list.
            send_to.append({'contact_field': old_primary_contact_field,
                            'contact_value': old_image[old_primary_contact_field]['S']
                            })
            send_to.append({'contact_field': new_primary_contact_field,
                            'contact_value': new_image[new_primary_contact_field]['S']
                            })
            primary_contact_change = 'We have processed a request to update your primary contact method from %s to %s.\n' \
                                     'If you did not request this change please reach out to the security department.\n' \
                                     'A copy of this notice has been sent to both locations.\n' % \
                                     (old_image['primary_contact_method']['S'], new_image['primary_contact_method']['S'])
        # check if the value in the primary contact field has changed
        elif old_image[new_primary_contact_field] != new_image[new_primary_contact_field]:
            # If so, add both the old primary contact and the new primary contact to the send to list.
            send_to.append({'contact_field': new_primary_contact_field,
                            'contact_value': old_image[new_primary_contact_field]['S']
                            })
            send_to.append({'contact_field': new_primary_contact_field,
                            'contact_value': new_image[new_primary_contact_field]['S']
                            })
            primary_contact_change = 'We have processed a request to update your primary contact from %s to %s.\n' \
                                     'If you did not request this change please reach out to the security department.\n' \
                                     'A copy of this notice has been sent to both locations.\n' % \
                                     (old_image[new_primary_contact_field]['S'], new_image[new_primary_contact_field]['S'])
        else:
            # If the primary contact method and the primary contact value did not change, only send to the primary contact
            send_to.append({'contact_field': new_primary_contact_field,
                            'contact_value': new_image[new_primary_contact_field]['S']
                            })
        # figure out other changes
        if name_change is None and primary_contact_change is None:
            other_change = 'Your contact record has been updated.\n'
        message = name_change if name_change is not None else '' \
            + primary_contact_change if primary_contact_change is not None else '' \
            + other_change if other_change is not None else ''
        for send in send_to:
            result.append(message_handler('mail' if send['contact_field'] == 'address' else send['contact_field'],
                                          send['contact_value'], message))
    except KeyError as e:
        result.append(error_handler('KeyError', cur_function, e))
    except Exception as e:
        result.append(error_handler('Exception', cur_function, e))
    return result


def name_builder(new_image):
    # name = ''
    # make sure first and last name exist in the new image. If they do, check if they are strings and handle accordingly
    if "last_name" in new_image and "first_name" in new_image:
        name = '%s %s' % (new_image['first_name']['S'], new_image['last_name']['S']) \
            if isinstance(new_image['first_name']['S'], str) and isinstance(new_image['last_name']['S'], str) \
            else '%s' % new_image['first_name']['S'] if isinstance(new_image['first_name']['S'], str) \
            else '%s Household' % new_image['last_name']['S'] if isinstance(new_image['last_name']['S'], str) \
            else 'Friend of the Organization'
    # if only first name exists, make sure it is a string and handle accordingly
    elif "first_name" in new_image:
        name = '%s' % new_image['first_name']['S'] if isinstance(new_image['first_name']['S'], str) \
            else 'Friend of the Organization'
    # if only last name exists, make sure it is a string and handle accordingly
    elif "last_name" in new_image:
        name = '%s Household' % new_image['last_name']['S'] if isinstance(new_image['last_name']['S'], str) \
            else 'Friend of the Organization'
    # otherwise, use generic
    else:
        name = 'Friend of the Organization'
    return name


def get_primary_contact_field(primary_contact_method):
    return 'address' if primary_contact_method == 'mail' else primary_contact_method


def message_handler(contact_method, contact_value, message):
    cur_function = inspect.currentframe().f_code.co_name
    if contact_method == 'email':
        result = email_handler(contact_value, message)
    elif contact_method == 'phone':
        result = phone_handler(contact_value, message)
    elif contact_method == 'sms':
        result = sms_handler(contact_value, message)
    elif contact_method == 'mail':
        result = mail_handler(contact_value, message)
    else:
        result = error_handler('BadData', cur_function, 'Invalid contact method: %s' % contact_method)
    return result


def email_handler(email, message):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        print('\nThis is just a stub function for handling email functionality.')
        print('Sending email to: %s' % email)
        print('Message :\n%s' % message)
        print('\nIf this were a real email handler, it would call an API which would trigger the email message.\n****\n')
        result = {"function": cur_function, "result": "success"}
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    logging.info(result)
    return result


def phone_handler(phone, message):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        print('\nThis is just a stub function for handling phone functionality.')
        print('Calling: %s' % phone)
        print('Rrriiinnnggg  rrriiinnnggg!')
        print('Message :\n%s' % message)
        print('\nIf this were a real phone handler, it would send this to a call center or something...\n****\n')
        result = {"function": cur_function, "result": "success"}
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    logging.info(result)
    return result


def sms_handler(sms, message):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        print('\nThis is just a stub function for handling sms functionality.')
        print('Sending sms to: %s' % sms)
        print('Message :\n%s' % message)
        print('\nIf this were a real sms handler, it would call an API which would trigger the sms message.\n****\n')
        result = {"function": cur_function, "result": "success"}
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    logging.info(result)
    return result


def mail_handler(address, message):
    cur_function = inspect.currentframe().f_code.co_name
    try:
        print('\nThis is just a stub function for handling mail functionality.')
        print('Sending mail to: %s' % address)
        print('Message :\n%s' % message)
        print('\nIf this were a real mail handler, it would add the record to a mail file for printing and mailing.\n****\n')
        result = {"function": cur_function, "result": "success"}
    except Exception as e:
        result = error_handler('Exception', cur_function, e)
    logging.info(result)
    return result


