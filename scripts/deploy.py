#!/usr/bin/python3

import argparse, pip, sys, time, json
try:
    __import__('marathon')
except ImportError:
    pip.main(['install', 'marathon==0.9.0'])
from marathon import MarathonClient, MarathonApp
from marathon.exceptions import MarathonHttpError

def check_deployment(c,new_app_id):
    print("Deployment in progress...")
    time.sleep(5)
    while True:
        app = c.get_app(new_app_id)
        time.sleep(5)
        if app.last_task_failure is not None:
            print ("Something went wrong! Cancelling this deployment...")
            c.scale_app(new_app_id, instances=0, delta=None, force=True)
            sys.exit(app.last_task_failure.message)
        if len(app.deployments) == 0:
            break

def check_health(c,new_app_id):
    # Currently, for apps with multiple health checks, if the first reports healthy
    # the app is marked as healthy during deployment. Add a double-check of the health if any
    # deployment is marked as successful and that is not true. Timeout after 120s.
    # There is already a jira issue on Mesosphere's tracker to give this implementation more context
    # In the meantime, this should provide a barrier for apps that do not pass all checks.
    print ("Re-checking health...")
    timeout = time.time() + 120
    app = c.get_app(new_app_id)
    if app.tasks is not None:
        print ("\nWaiting for", new_app_id, "tasks to become completely healthy...")
        while True:
            print ("Total Tasks:", len(app.tasks),
                   "| Healthy Tasks:", app.tasks_healthy,
                   "| Unhealthy Tasks:", app.tasks_unhealthy,
                   "| Staged Tasks:", app.tasks_staged)
            if len(app.tasks) == app.tasks_healthy:
                print ("All tasks are healthy!\n")
                return
            elif time.time() > timeout:
                print ("Health checks keep failing, cancelling this deployment...")
                c.scale_app(new_app_id, instances=0, delta=None, force=True)
                sys.exit()
            time.sleep(2)

def scale(c,new_app_id,old_appid,delta):

    print ("Scaling up new version by", delta, "instances...")
    c.scale_app(new_app_id, delta=delta)
    check_deployment(c,new_app_id)
    check_health(c,new_app_id)

    time.sleep(5)
    if c.get_app(old_appid).instances>0:
        print ("Scaling down old version by", delta, "instances...")
        c.scale_app(old_appid, delta=-(delta if delta <= c.get_app(old_appid).instances else c.get_app(old_appid).instances))
        check_deployment(c,old_appid)

def deploy(app_definition,marathon_url,instances,auth_token,zero,force):
    old_appids = []
    # Connect to Marathon
    print ("\nConnecting to Marathon...")
    c = MarathonClient(marathon_url, auth_token=auth_token)
    print ("Connected to", marathon_url)

    # Pick up the Marathon App Definition file
    app_json = open(app_definition).read()
    app = MarathonApp.from_json(json.loads(app_json))
    new_app_id = app.id
    service_name = new_app_id.split("/")[-1].split(".")[0]

    # Instantiate the new application on DC/OS but don't launch it yet
    # The application definition instances field should be 0 by default
    # If forced, the application will be relaunched even if the ID already exists
    print ("\nInstantiating new application on Marathon with", app.instances, "instances...")
    try:
        c.create_app(new_app_id, app)
    except:
        if force == 'Yes':
            print ("\nForcing redeploy of the same app id...", new_app_id)
            c.update_app(new_app_id, app, force=True, minimal=True)
            check_deployment(c,new_app_id)
            pass
        else:
            sys.exit()
    print ("Created app", new_app_id)

    # List and find currently running apps of the same service
    # This assumes the naming convention (id): /some/group/service_name.uniquevalue
    print ("\nFinding any existing apps for service:", service_name)
    for app in c.list_apps():
        existing_service_name = app.id.split("/")[-1].split(".")[0]
        if (service_name == existing_service_name) and app.instances > 0:
            print ("Found up and running application id:", app.id)
            old_appids.append(app.id)

    # If it's the first deployment ever, just launch the desired number of instances
    # Otherwise perform a hybrid release
    # Finally clean up any older app instances running
    if not old_appids:
        if instances is None:
            instances = 2
        print ("No current apps found. Launching brand new service with", instances, "instances...")
        c.scale_app(new_app_id, instances=instances)
        check_deployment(c,new_app_id)
        check_health(c,new_app_id)

    else:
        old_appids.reverse()
        if zero == 'Yes':
            print ("\nStarting zero downtime deployment for...", new_app_id)
            for old_appid in old_appids:
                if instances is None:
                    instances = c.get_app(old_appid).instances
                if (old_appid == '' or old_appid == new_app_id or old_appid == '/'+new_app_id):
                    print ("Scaling existing app_id", new_app_id, "to", instances, "instances...")
                    c.scale_app(new_app_id, instances=instances)
                    check_deployment(c,new_app_id)
                    check_health(c,new_app_id)

                else:
                    print ("Target number of total instances:", instances)
                    delta = int(round(instances*.50))
                    delta = (delta if delta >0 else 1)

                    scale(c,new_app_id,old_appid,delta)

                    if (c.get_app(new_app_id).instances != instances):
                        print ("\nLaunch", instances - delta, "remaining instance(s) of the new version...")
                        c.scale_app(new_app_id, instances=instances)
                        check_deployment(c,new_app_id)
                        check_health(c,new_app_id)
                    if (c.get_app(old_appid).instances > 0):
                        print ("Finish shutting down remaining instances of the old version...")
                        c.scale_app(old_appid, instances=0)
                        check_deployment(c,old_appid)
        else:
            print ("Started deployment with downtime...")
            for old_appid in old_appids:
                c.scale_app(old_appid, instances=0)
                check_deployment(c,old_appid)
            c.scale_app(new_app_id, instances=instances)
            check_deployment(c,new_app_id)
            check_health(c,new_app_id)

    print ("\nSUCCESS:\nNew application ID:", new_app_id, "\nRunning instances:", instances)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--app-definition', help='Application definition file path', required=True)
    parser.add_argument('-m', '--marathon-url', help='Marathon URL', required=True)
    parser.add_argument('-i', '--instances', help='Number of instances to deploy', type=int, required=False)
    parser.add_argument('-c', '--credential', help='JWT used to authenticate with Marathon (for open source DC/OS)', required=True)
    parser.add_argument('-z', '--zero-down', help='Yes/No Run a zero down time. If no, then scale all the others apps to zero and then scale the new app', required=False, default='Yes')
    parser.add_argument('-f', '--force', help='Force recreation of the application if the id already exists', required=False, default='No')
    args = parser.parse_args()
    app_definition = args.app_definition
    marathon_url = args.marathon_url
    instances = args.instances
    auth_token = args.credential
    zero = args.zero_down
    force = args.force
    try:
        print ("Starting...")
        deploy(app_definition,marathon_url,instances,auth_token,zero,force)
    except:
        print ("Unexpected error:", sys.exc_info()[0])
        raise

if __name__ == "__main__":
    main()
