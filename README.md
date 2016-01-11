# Courier

`courier` is a service for deploying configuration for Armada service independently from the image of the service, to
quickly make the impact of configuration change. 

In Armada ecosystem, Courier is used for fetching configuration files from (git) repository and sending it to
datacenters where the services are running.

Since not always there is a direct access from various datacenter's servers to git repository, multiple Couriers can be
organized in flexible architecture to enable that.


Configurations can be stored in the same repository as the service, or in separate repositories. Courier covers both
these cases.

Courier uses rsync to send the configurations and supports SSH tunnels.

# Building and running the service

    armada build courier
    armada run courier

# Configuration

`courier` is configured using Hermes.

## Sources

Configuration of the sources are taken from all .json files found in `sources` directory.

There are currently two types of sources: `git` and `hermes-directory`.

### Git source

#### Example of "git" source .json file for the case when configurations are stored in separate repositories:

    [
        {
            "type": "git",
            "repositories": [
                "ci@git.initech.com:checkers/checkers-config.git",
                "ci@git.initech.com:go/go-config.git"
            ],
            "branch": "dev",
            "ssh_key": "../keys/ci@git.initech.com.key",
            "destinations": [
                "courier@sandbox"
            ]
        }
    ]
    

    
* `repositories` is a list of git SSH addresses from which the configurations will be taken.

* `branch` is an optional parameter with git branch. Default is "master".

* `ssh_key` is a path to SSH key file for git authorization. It is relative to the source .json file.

* `destinations` is a list of destination aliases to which the config will be pushed. They have to be defined in
`destinations.json` config file. See "Destinations" section.


#### Example of "git" source .json file for the case when configuration is stored in subdirectory of the service repository:

    [
        {
            "type": "git",
            "repositories": [
                "ci@git.initech.com:chess/chess.git"
            ],
            "subdirectory": "config",
            "destination_path": "chess-config",
            "branch": "dev",
            "ssh_key": "../keys/ci@git.initech.com.key",
            "destinations": [
                "courier@sandbox"
            ]
        }
    ]

* `subdirectory` is an optional parameter pointing to subdirectory with configuration inside the repository.
If not provided courier will take the entire repository.

* `destination_path` is an optional parameter that is the name of directory on destination server into which Courier
will push the source directory. By default it is the name of repository. **If it is set, then only one repository can be
provided.**

### Hermes-directory source

Another type of source is "hermes-directory". Example:

    [
        {
            "type": "hermes-directory",
            "subdirectory": "to-upload",
            "destination_directory": "uploaded",
            "destinations": ["armada@office"]
        }
    ]

It will take the contents of subdirectory in "hermes-directory" - `/etc/opt/to-upload` and push it to defined
destinations. After updating courier, it be available on destinations in `/etc/opt/uploaded`.

`subdirectory` and `destination_directory` fields are optional.
If `destination_directory` is not provided, the `subdirectory` will be taken.
If `subdirectory` is not provided, the entire `/etc/opt` will be pushed.

The `hermes-directory` source type can be useful if the Courier does not have direct access to git (e.g. Courier on
production server that is supposed to distribute configuration to other ships in cluster).

See `POST /update_from_hermes_directory` in [API](#api) section to learn about updating specific "hermes-directory"
source.

## Destinations

Destinations can be defined in `destinations.json` config file.

This example illustrates real life case with three datacenters: office, sandbox, production:

    {
        "armada@office":
        {
            "type": "armada-local"
        },
        "courier@sandbox":
        {
            "type": "courier-remote",
            "address": "courier.sandbox.initech.com"
        },
        "courier@production":
        {
            "type": "courier-remote",
            "address": "courier.production.initech.com",
            "ssh-tunnel": {
                "host": "gateway.initech.com",
                "port": "20022",
                "user": "deploy",
                "key": "keys/deploy@gateway.initech.com.key"
            }
        }
    }
    
There are three destination aliases defined `armada@office`, `courier@sandbox` and `courier@production`.

The first `armada@office` has `armada-local` type which tells Courier to send configurations to all Armada agents in
the same Armada cluster that Courier is running in. This will effectively put these configurations into `/etc/opt` on
all Armada ships in the cluster, since Armada's hermes-directory is mounted there, making them available for services 
configured using Hermes. Thanks to that, one Courier per Armada cluster is enough.

The second `courier@sandbox` has `courier-remote` type which tells Courier to send the configuration to some other
Courier, running on the address `courier.sandbox.initech.com`.

If the remote courier address cannot be accessed directly (e.g. only from internal network in production) then SSH
tunnel can be used as intermediary connection, as seen in `courier@production`.



Let's assume that production Armada cluster consists of multiple ships. Then production Courier
(aliased: `courier@production`) should take care of distributing the configuration among them. To configure it, it is
enough that it has `source.json` config defined as follows:

    [
        {
            "type": "hermes-directory",
            "destinations": ["armada@production"]
        }
    ]

and `destinations.json` as:

    {
        "armada@production":
        {
            "type": "armada-local"
        }
    }



# API

* `GET /` - Displays welcome message of the Courier and its environment and app_id.

* `GET /hermes_address` - Returns Hermes-address of the Courier in the form
`{"path": "/tmp/hermes-directory", "ssh": "192.168.0.100:32772"}`.
It is used by other Couriers to determine the destination path for configurations and its SSH address used by rsync.
Armada agents also have `GET /hermes_address` endpoint, which is used by destination type `armada-local`. 

* `POST /update_hermes` - Sends configurations from all sources to given Hermes-address. It has to be provided in the
body as JSON in the form `{"path": "/tmp/hermes-directory", "ssh": "192.168.0.100:32772"}`.
It can be used to transfer configuration from one courier to another courier or armada agent.
It is used internally by Armada to get the latest configs on start/restart. 

* `POST /update_from_git` - Sends configurations from all sources that are pointing to given git repository. It has to
be provided in the body as JSON in the form `{"url": "ci@git.initech.com:chess/chess.git", "branch": "master"}`.

* `POST /update_from_hermes_directory` - Sends configurations from sources of type `hermes-directory` with
`subdirectory` equal to the one sent in JSON body via POST. Example: `{"subdirectory": "to-upload"}`.

* `POST /update_all` - Sends configurations from all sources to their defined destinations. It is triggered on remote
Couriers after pushing configurations to them.

* `POST /gitlab_web_hook` - Endpoint for GitLab's push Web Hook. See more in "GitLab integration" section.

# GitLab continuous integration

You can set up a push Web Hook in GitLab so it automatically updates configurations on all defined hosts after pushing
to certain git repositories.

Instructions to set it up:

* Go to project's GitLab web page.

* Go to "Settings".

* Go to "Web Hooks".

* Type Courier address in URL field. This Courier needs to have access to the git repository and have defined source
for it.

* Make sure "Push events" trigger is checked.

* Click "Add Web Hook".

Then, after you push a change to configuration repository, Courier will take care of delivering it to your Armada
clusters.
However, it is up to the services how and when they reload the configuration.
