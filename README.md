# Marathon Utilities

Some scripts to interact with [Marathon](https://github.com/mesosphere/marathon) on DC/OS. Uses Python 3.6 and [marathon-python](http://thefactory.github.io/marathon-python/) client 0.9.0.

### No downtime deployment

Only useful if you use an unique `id` for the same application, such as `"id": "nginx.v1"`, `"id": "nginx.v2"`, and so on. Supports remote authentication for open source DC/OS if you have previously generated a JWT.

To run the script locally:

`$ python marathon-utils/scripts/deploy.py -a <APP_DEFINITION_PATH> -m <MARATHON_ENDPOINT> -c <MARATHON_JWT>`

Or build the Docker image and run it inside.

To force the recreation of the application if the `id` already exists, use `-f`.

It works just fine, but I abandoned it halfway through, so take it with a grain of salt.