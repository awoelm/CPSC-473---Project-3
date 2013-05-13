import sqlite3, sha, time, Cookie, os, datetime, hashlib
from bottle import get, post, route, debug, run, template, request
from bottle import static_file, url, response, redirect, install
from bottle_redis import RedisPlugin

import constants, account

#
#      Key: task:ano:eno:tno
#      Fields:      'tname' : tname,                        str
#                   'tinfo' : tinfo,                        str
#                   'tcost' : tcost,                        not sure what this is? money? double?
#                   'tstatus' : tstatus,                    int - from constatns
#                   'numitems' : numitems                   int
#

def create_task(rdb):
    try:
        #get incoming fields
        event_id = request.POST.get('event_id','').strip()
        tname = request.POST.get('task_name','').strip()
        tinfo = request.POST.get('task_info','').strip()
        tcost = request.POST.get('task_cost','').strip()
        tstatus = request.POST.get('task_status','').strip()
        
        #get current user info
        user = request.get_cookie('account', secret='pass')
        user_id = str(int(rdb.zscore('accounts:usernames', user)))

        #Increment numtasks to get new task_id
        task_id = int(rdb.hget('event:' + user_id + ':' + event_id, 'numtasks')) + 1

        task_key = 'task:%s:%s:%s' % (user_id, event_id, str(task_id))
        
        #Add event info to db
        rdb.hmset(task_key,
                 {  'tname' : tname, 
                    'tinfo' : tinfo, 
                    'tcost' : tcost,
                    'tstatus' : constants.getStatusIntFromStr(tstatus), 
                    'numitems' : 0
                 })
                 
        #update event's task count
        rdb.hincrby('event:' + user_id + ':' + event_id, 'numtasks', 1)
        
        return (user_id,  event_id, task_id)
    
    except:
        return None
    
    
