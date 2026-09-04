## Purpose

Defines the self-hosted Docker Compose deployment topology (Temporal, MongoDB, and a
GPU-capable worker) that every later Narrator Studio capability runs on, with no
application logic of its own.

## ADDED Requirements

### Requirement: Full stack starts with a single command
The system SHALL bring up every service in the stack (Temporal server, its datastore,
Temporal Web UI, MongoDB, and the GPU worker stub) from a clean state using one
Docker Compose command, with no manual per-service steps required.

#### Scenario: Clean start
- **WHEN** `docker compose up -d` is run against a host with no prior stack state
- **THEN** every defined service reaches a running/healthy state without manual
  intervention

### Requirement: Temporal server is reachable
The system SHALL expose the Temporal server's frontend service such that a client can
connect and receive a healthy response.

#### Scenario: Client connects to Temporal
- **WHEN** a gRPC client connects to the Temporal frontend service's configured port
- **THEN** the connection succeeds and the server reports a healthy status

### Requirement: Temporal Web UI is reachable
The system SHALL expose Temporal's built-in Web UI over HTTP.

#### Scenario: Operator opens the Temporal Web UI
- **WHEN** an HTTP client requests the Temporal Web UI's configured port
- **THEN** it returns a successful (2xx) response

### Requirement: MongoDB is reachable and persists data across restarts
The system SHALL expose MongoDB such that a client can connect, and data written to it
SHALL survive a container restart.

#### Scenario: Data survives a restart
- **WHEN** a client connects to MongoDB, writes a test document, the `mongo` container
  is then restarted, and the client reconnects
- **THEN** the previously written document is still readable

### Requirement: GPU worker container has functioning GPU access
The GPU worker stub container SHALL have access to the host's GPU without requiring
explicit per-container GPU flags, since the host's Docker daemon is configured with
`nvidia` as the default runtime.

#### Scenario: Stub container detects the GPU
- **WHEN** the GPU worker stub container starts
- **THEN** it reports GPU/CUDA availability as true and logs the detected device name

### Requirement: Worker images round-trip through the private registry
The system SHALL support building a worker image, pushing it to the existing private
registry, and pulling it back down to run identically.

#### Scenario: Push and pull round trip
- **WHEN** the GPU worker stub image is built, tagged for
  `docker-registry.mixwarecs-home.net:5000`, pushed, and then pulled fresh on the same
  host
- **THEN** the pulled image starts and reports the same GPU-detection result as the
  originally built image
