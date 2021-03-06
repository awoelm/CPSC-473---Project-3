import sqlite3, sha, time, Cookie, os, datetime, hashlib
from bottle import get, post, route, debug, run, template, request
from bottle import static_file, url, response, redirect, install
from bottle_redis import RedisPlugin

import constants, account

########################################################################
#create_event - create a new event entry in redis db
#   param   - rdb - redis db ojbect passed by plugin
#   return  - touple - (user's id, events id) if creation is successful
#                      None if creation failed
########################################################################
def create_event(rdb):
    try:
        #get incoming fields
        etype = request.POST.get('visibility','').strip()
        estatus = request.POST.get('status','').strip()
        eduedate = request.POST.get('datepicker','').strip()
        eventdesc = request.POST.get('event_description','').strip()
        ename = request.POST.get('event_name','').strip()
        #print ename, eventdesc, eduedate, etype

        #get current user info
        user = request.get_cookie('account', secret='pass')
        user_id = str(int(rdb.zscore('accounts:usernames', user)))
        #print user, user_id

        #Increment number of user's events, get new value:
        event_id = str(rdb.hincrby('account:' + user_id, 'numevents', 1))
        #print event_id

        #Add event info to db
        rdb.hmset('event:' + user_id + ':' + event_id,
                 {  'ename' : ename, 
                    'eduedate' : eduedate, 
                    'eventdesc' : eventdesc,
                    'numinvited' : 0, 
                    'responded' : 0,
                    'numattending' : 1,
                    'estatus' : constants.getStatusIntFromStr(estatus),
                    'etype' : constants.getEventTypeFromStr(etype), 
                    'numtasks' : 0 })
        
        #add event to its respective lists
        if constants.getEventTypeFromStr(etype) == constants.EVENT_TYPE_PUBLIC:
            #add event to public list
            rdb.sadd('events:public', 'event:' + user_id + ':' + event_id)
            #add event to user's public list
            rdb.sadd('account:' + user_id + ':public', 'event:' + user_id + ':' + event_id)
        else:
            #add even to user's private list
            rdb.sadd('account:' + user_id + ':private', 'event:' + user_id + ':' + event_id)
        
        #add owner to admin list for this event
        rdb.sadd('eventadmins' + user_id + ':' + event_id, user_id)
        
        return (user_id,  event_id)
    except:
        return None
