import sha, time, Cookie, os, datetime, hashlib
from bottle import get, post, route, debug, run, template, request, validate
from bottle import static_file, url, response, redirect, install
from bottle_redis import RedisPlugin

import account, event, constants

install(RedisPlugin())


########################################################################
#                         Redis Notes                         #
########################################################################
#   Hash tables:
#
#      Key: account:no
#       Fields:     'firstname' : firstname,                str
#                   'lastname' : lastname,                  str
#                   'useremail' : useremail,                str
#                   'username' : username,                  str
#                   'password' : password,                  str
#                   'salt' : salt                           str
#
#      Key: event:ano:eno
#       Fields:		'ename' : ename,                        str
#                   'eduedate' : eduedate,                  datetime
#                   'eventdesc' : eventdesc,                str
#                   'numinvited' : numinvited,              int
#                   'responded' : responded,                int
#                   'numattending' : numattending,          int
#                   'estatus' : 'estatus',                  int - from constants
#                   'etype' : etype,                        int - from constants
#                   'numtasks' : numtasks                   int
#
#  --Removed public field from event, not sure what this was for, the
#    etype is there to determine public/private
#
#      Key: task:ano:eno:tno
#      Fields:      'tname' : tname,                        str
#                   'tinfo' : tinfo,                        str
#                   'tcost' : tcost,                        double
#                   'tstatus' : tstatus,                    int - from constatns
#                   'numitems' : numitems                   int
#
#      Key: item:ano:eno:tno:ino
#      Fields:		'iname' : iname,                        str
#                   'icost' : icost,                        double
#                   'inotes' : inotes,                      str
#                   'istatus' : istatus                     int - from constants
#
#   Sets:
#       accounts:usernames                          // Sorted Set of all usernames
#       accounts:emails                             // Set of all user emails
#       account:no:public                           // Set of all public events this account owns
#       account:no:private                          // Set of all private events this account owns
#       account:no:invited                          // Set of all events this account has been invited to help plan
#       events:public                               // Set of all public events
#       eventadmins:owneracctno:eventno             // Set of all accounts allowed to modify this event
#
#   CONSIDERATIONS:
#       Invitations, there are 2 meanings here:
#           1: Event numinvited -   This is the number of invitations the user has sent out.
#           2: Account invited -    This is a set of events the user has been invited to help plan.
########################################################################


########################################################################
#                         View Functions                         #
########################################################################

@get('/')
def default_route():
    logged_in = account.isLoggedIn()
    
    return template('default.tpl', get_url=url, logged_in=logged_in)


@get('/login')
def login_route():
    logged_in = account.isLoggedIn()
    if logged_in:
        redirect('/userhome')
    else:
        return template('login.tpl', get_url=url, logged_in=logged_in)


@post('/login')
def login_submit(rdb):
    username = request.POST.get('username','').strip()
    password = request.POST.get('password','').strip()
    
    if account.check_login(rdb, username, password):
        response.set_cookie('account', username, secret='pass', max_age=600)
        redirect('/userhome')
    else:
        return template('loginfail.tpl', get_url=url, logged_in=False)


@get('/logout')
def logout_route():
    if account.isLoggedIn():
        response.delete_cookie('account', secret='pass')
    redirect('/login')

@post('/userhome')
@get('/userhome')
def userhome_route(rdb):
    if account.isLoggedIn():
        user = request.get_cookie('account', secret='pass')
        user_id = str(int(rdb.zscore('accounts:usernames', user)))
        
        #get list of private events for current user
        lstprivates = getUserEventsList(rdb, user_id, 'private')
        
        #get list of invited to events for current user
        lstinvited = getUserEventsList(rdb, user_id, 'invited')
        
        #get list of public events for current user
        lstpublics = getUserEventsList(rdb, user_id, 'public')
        
        return template('userhome.tpl',public_events=lstpublics,private_events=lstprivates,
                        invited_events=lstinvited, get_url=url, logged_in=True)
    else:
        redirect('/login')
        


@get('/signup')
def signup_route():
    if account.isLoggedIn():
        redirect('/userhome')
    else:
        logged_in = False
        return template('signup.tpl', get_url=url, logged_in=logged_in)


@post('/signup')
def signup_submit(rdb):
    result = account.create_account(rdb)
    print result
    if result:
        redirect('/userhome')
    else:
        return template('loginfail.tpl', get_url=url, logged_in=result)


@get('/modifyacct')
def modifyacct_route(rdb):
    logged_in = account.isLoggedIn()
    if logged_in:
        info = account.getUserModInfo(rdb)
        return template('modifyacct.tpl', get_url=url, logged_in=logged_in, acct=info)
    else:
        redirect('/login')


@post('/modifyacct')
def modifyacct_submit(rdb):
    result = account.modify_account(rdb)
    print result
    if result:
        return template('userhome.tpl', get_url=url, logged_in=result)
    else:
        return "Failed to modify account."


@get('/newevent')
def newEvent_route():
    logged_in = account.isLoggedIn()
    if logged_in:
        return template('newevent.tpl', get_url=url, logged_in=logged_in)
    else:
        redirect('/login')


@post('/newevent')
def newEvent_submit(rdb):
    result = event.create_event(rdb)
    #   result = (user_id , event_id)
    if result:
        redirect('/event/%s/%s' % result)
    #event created
    else:
        #failed to create event
        return "Failed to create event"

@post('/event/<user_id:re:\d+>/<event_id:re:\d+>')
def add_newtask(rdb, user_id, event_id):
    logged_in = account.isLoggedIn()
    if logged_in:
        return template('newtask.tpl', get_url=url, logged_in=logged_in, event_id=event_id)
    else:
        redirect('/userhome')

@get('/event/<user_id:re:\d+>/<event_id:re:\d+>')
def show_event(rdb, user_id, event_id):
    
    logged_in = account.isLoggedIn()
    if logged_in:   
        #get event info
        event_info = rdb.hgetall('event:' + str(user_id) + ':' + str(event_id))
        
        #add string versions of constants
        event_info['strestatus'] = constants.getEventTypeStrFromInt(event_info['estatus'])
        event_info['stretype'] = constants.getStatusStrFromInt(event_info['etype'])
        event_info['user_id'] = user_id
        event_info['event_id'] = event_id
        
        #get tasks for this event
        tasks = []
        for i in range(1, int(event_info['numtasks'])):
            #get task
            task_info = rdb.hgetall('task:' + str(user_id) + ':' + str(event_id) + ':' + str(i))
            print task_info
            t = (   i,
                 task_info['tname'],
                 task_info['tinfo'],
                 task_info['tcost'],
                 constants.getStatusStrFromInt(task_info['tstatus']),
                 task_info['numitems'],
                 [])
            #get items for each task
            for j in range(1, int(task_info['numitems'])):
                #get task
                item_info = rdb.hgetall('item:' + str(user_id) + ':' + str(event_id) + ':' + str(i) + ':' + str(j))
                item = (j,
                        item_info['iname'],
                        item_info['icost'],
                        item_info['inotes'],
                        constants.getStatusStrFromInt(item_info['istatus']) )
                t[7].insert(0, item)
            
            tasks.insert(0,t)
            #return info to template
            event_info['tasks'] = tasks
        
        return template('event.tpl', get_url=url, logged_in=logged_in, row=event_info)
    
    else:
        redirect('/userhome')


# INCOMPLETE
@get('/delevent/<user_id:re:\d+>/<event_id:re:\d+>')
def delete_event(rdb, user_id, event_id):
    #ensure this event is owned by the current user
    user = request.get_cookie('account', secret='pass')
    cur_user_id = str(int(rdb.zscore('accounts:usernames', user)))
    if cur_user_id != user_id:
        return "Access Denied!"
        
    numtasks = rdb.hget('event:' + user_id + ':' + event_id, 'numtasks')
    
    #get all tasks for this event
    for i in range(0, numtasks):
        #get all items for this task and delete
        numitems = rdb.hget('task:' + user_id + ':' + event_id + ':' + i)
        for j in range(o, numitems):
            rdb.delete('item:' + user_id + ':' + event_id + ':' + i + ':' + j)
        rdb.delete('task:' + user_id + ':' + event_id + ':' + i)
    #delete the event
    rdb.delete('event:' + user_id + ':' + event_id)
    
    if rdb.sismember('events:public', 'event:' + user_id + ':' + event_id):
        rdb.srem('event:' + user_id + ':' + event_id)
        
    #TODO: delete items from the other sets here
    return redirect('/userhome')


@get('/newtask')
def newTask_route(user_id, event_id):
    logged_in = account.isLoggedIn()
    if logged_in:
        return template('newtask.tpl', get_url=url, logged_in=logged_in, event_id=event_id)
    else:
        redirect('/login')


@post('/newtask')
def newTask_submit(rdb):
    result = task.create_task(rdb)
    print result
    #   result = (user_id , event_id)
    if result:
        #Where to redirect? show_task or show_event?
        #Currently redirect to show_event
        redirect('/event/%s/%s' % result)
    #task created
    else:
        #failed to create event
        return "Failed to add task"

@get('/newitem')
def newItem_route():
    logged_in = account.isLoggedIn()
    if logged_in:
        return template('newitem.tpl', get_url=url, logged_in=logged_in)
    else:
        redirect('/login')


@post('/newitem')
def newItem_submit(rdb):
    result = item.create_item(rdb)
    #   result = (user_id , event_id)
    if result:
        #Where to redirect? show_item, show_task, or show_event?
        #Currently redirect to show_event
        redirect('/event/%s/%s' % result)
    #item created
    else:
        #failed to create event
        return "Failed to add item"
    

@get('/:path#.+#', name='static')
def static(path):
    return static_file(path, root='')
    

@get('/ajax.js')
def js():
    return static_file('ajax.js', root='')


########################################################################
#                         Helper Functions                         #
########################################################################

########################################################################
#getUserEventsList - gets the event description, event status, event type, and event due date
#   param   - rdb - redis db ojbect passed by plugin
#           - no - account number
#           - pkey - partial key used to access a set (will either be 'private', 'public', or 'invited')
#   return  - lst - the list of information gathered
########################################################################

def getUserEventsList(rdb, no, pkey):
    print "getUserEventsList entered"
    print pkey
    lst = []
    event_ids = rdb.smembers('account:' + no + ':' + pkey)
    print event_ids
    
    #Use the ID's to retrieve the event information we're looking for
    if event_ids and event_ids != 'None':
        for i in event_ids:
            info = []
            info.insert(0, i)
            #inserting each field individually to make sure order is as expected.
            info.insert(1, rdb.hget(i, 'ename'))
            info.insert(2, rdb.hget(i, 'eventdesc'))
            info.insert(3, rdb.hget(i, 'estatus'))
            info.insert(4, rdb.hget(i, 'etype'))
            info.insert(5, rdb.hget(i, 'eduedate'))
            lst.insert(0,  (info))
    
    return lst


debug(True)
run(reloader=True)
