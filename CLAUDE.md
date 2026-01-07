# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tobiko is an OpenStack testing framework focusing on system-level operations and workload testing, complementary to Tempest (which focuses on REST API testing). It simulates real user behavior by:
- Creating workloads (Nova instances, networks, etc.)
- Executing disruption operations (service restarts, node reboots)
- Validating workload functionality after disruptions
- Testing upgrade/update scenarios

**Key differentiator**: White-box testing capabilities with SSH access to cloud nodes for internal inspection.

## Development Commands

### Running Tests

```bash
# Run unit tests
tox -e py3

# Run specific test file
tox -e py3 -- tobiko/tests/unit/path/to/test_file.py

# Run specific test case
tox -e py3 -- tobiko/tests/unit/path/to/test_file.py::TestClass::test_method

# Run functional tests (requires OpenStack cloud)
tox -e functional

# Run with coverage
tox -e cover
```

### Linting and Static Analysis

```bash
# Run all linters (flake8, mypy, pylint)
tox -e linters

# Run specific linters
tox -e pep8     # flake8 only
tox -e mypy     # mypy only
tox -e pylint   # pylint only

# Pre-commit hooks (runs automatically on commit)
pre-commit run -a
```

### Development Environment

```bash
# Create a development virtualenv with tobiko installed
tox -e venv

# Activate and use it interactively
tox -e venv -- bash
```

## Code Architecture

### Core Framework Components

**`tobiko/common/`** - Foundation layer
- `_fixture.py`: Fixture management system (extends Python fixtures library)
  - SharedFixture pattern: Fixtures that can be reused across test cases
  - Fixture manager for dependency resolution and lifecycle management
- `_case.py`: Base test case classes
- `_exception.py`: Custom exception hierarchy
- `_loader.py`: Dynamic loading of fixtures and test cases

**`tobiko/config.py`** - Configuration system
- Uses oslo.config for configuration management
- Configuration organized in groups (e.g., `CONF.tobiko.podified.*`)
- Module-specific configs registered via `register_tobiko_options()`
- Each module can have its own `config.py` with OPTIONS list

**`tobiko/openstack/`** - OpenStack integration
- Client wrappers for OpenStack services (Nova, Neutron, Glance, etc.)
- `stacks/`: Heat stack templates and fixture wrappers
- Test scenarios organized by service

**`tobiko/shell/`** - Shell and network utilities
- SSH client utilities
- Ping, HTTP ping, iperf3 monitoring tools
- Command execution framework

**`tobiko/podified/`** - Podified OpenStack (OpenShift-based) support
- `_openshift.py`: OpenShift/OCP client interactions using `openshift_client`
- `_topology.py`: Topology discovery and management
- Functions for managing EDPM nodes, OCP nodes, pods, and containers

**`tobiko/tripleo/`** - TripleO deployment support
- TripleO-specific topology and node management

**`tobiko/rhosp/`** - Red Hat OpenStack Platform specific features

### Configuration Pattern

When adding configurable values:

1. Define in module's `config.py`:
   ```python
   OPTIONS = [
       cfg.ListOpt('option_name',
                   default=['default', 'values'],
                   help='Description of the option.')
   ]
   ```

2. Register in `register_tobiko_options()`:
   ```python
   conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)
   ```

3. Use via `CONF`:
   ```python
   from tobiko import config
   CONF = config.CONF
   # Access as: CONF.tobiko.module_name.option_name
   ```

### Fixture Pattern

Tobiko uses a fixture-based architecture where resources are created and managed through fixtures:

```python
class MyFixture(tobiko.SharedFixture):
    def setup_fixture(self):
        # Create resources (called once, then shared)
        pass

    def cleanup_fixture(self):
        # Cleanup resources
        pass
```

Access fixtures using `tobiko.setup_fixture()` or `tobiko.get_fixture()`.

### Testing Against Different Deployments

The framework supports multiple OpenStack deployment types through topology abstraction:
- **DevStack**: Traditional all-in-one development setup
- **TripleO**: Undercloud/overcloud architecture
- **Podified**: OpenShift-based control plane with EDPM data plane

Topology detection happens automatically based on environment configuration.

## Code Quality Standards

- **Line length**: 79 characters (flake8 enforced)
- **Type hints**: Required for new code (mypy checked)
- **Import order**: PEP8 style
- Pre-commit hooks run flake8, mypy, and pylint automatically

### Import Best Practices

**IMPORTANT**: Before adding imports, check if the function/class is already exposed via `__init__.py`:

1. **Check `__init__.py` first**: Many commonly used functions are exposed at the module level
   - Example: `tobiko.get_object_name` is exposed in `tobiko/__init__.py` (from `tobiko.common._fixture`)
   - Use `grep "function_name" $(find -name __init__.py)` to search all `__init__.py` files

2. **Avoid circular imports**: Be aware of the import hierarchy
   - If module A imports from module B, then B should NOT import from A
   - Example: `tobiko/__init__.py` imports from `_lockutils`, so `_lockutils.py` cannot import `tobiko`

3. **Import from source when necessary**: If using an exposed function would cause circular imports, import directly from the source module
   - Example: Use `from tobiko.common import _fixture` in `_lockutils.py` instead of `import tobiko`

## Unit Testing Requirements

**IMPORTANT**: When adding new functionality or fixing bugs in `tobiko/` modules, always create corresponding unit tests under `tobiko/tests/unit/`:

- **Test location**: Create unit tests in `tobiko/tests/unit/` directory
- **Test naming**: Follow the pattern `test_<module_name>.py` (e.g., `test_lockutils.py` for `tobiko/common/_lockutils.py`)
- **Running tests**: Use `tox -e py3 -- tobiko/tests/unit/test_file.py` to run specific unit tests
- **Test structure**: Follow the existing test patterns using `testtools.TestCase`

Example:
```bash
# Create unit test for tobiko/common/_lockutils.py
# Location: tobiko/tests/unit/test_lockutils.py

# Run the unit test
tox -e py3 -- tobiko/tests/unit/test_lockutils.py

# Run a specific test method
tox -e py3 -- tobiko/tests/unit/test_lockutils.py::TestClass::test_method
```

## Git Commit Guidelines

When creating commits with Claude Code assistance, use the following format:

```
Short commit summary (imperative mood)

Optional detailed description explaining the change,
the motivation, and any relevant context.

Signed-off-by: <user>
Generated-By: <claude-model-in-use>
```

Replace `<claude-model-in-use>` with the actual model being used (e.g., `claude-sonnet-4-5`, `claude-opus-4-5`).

Always use the `-s` option with `git commit` to automatically add the `Signed-off-by` line.

### Choosing Between Generated-By and Assisted-By

- **Generated-By**: Use when the changes included in the commit were mainly generated by Claude (either directly editing files or suggested by Claude).
- **Assisted-By**: Use when Claude helped, but most of the changes were implemented by the user on their own.

When it is not clear which footer to use, Claude will ask the user to decide.

**Do not** use "Co-Authored-By:" footers.

### Pre-commit Hook

When the pre-commit hook is not installed, Claude should install it before running `git commit` by running:

```bash
python -m tox -e linters
```

### Amending Commits with Change-Id

When amending commits that include a `Change-Id:` line (used by Gerrit code review), **NEVER** modify or remove the Change-Id line. The Change-Id must remain exactly the same after amending to maintain the link to the code review.

Example of a commit with Change-Id:
```
Fix bug in configuration loader

This fixes an issue where configuration options were not
properly validated.

Generated-By: claude-model-xxx
Change-Id: I64928080e13c9ddc02df90291e988708258452e8
```

When amending this commit, preserve the `Change-Id: I64928080e13c9ddc02df90291e988708258452e8` line exactly as is.

## Environment Variables

Key environment variables for test execution:

- `OS_*`: OpenStack credential variables (OS_AUTH_URL, OS_USERNAME, etc.)
- `TOBIKO_*`: Tobiko-specific configuration overrides
- `KUBECONFIG`: Path to kubeconfig for podified deployments
- `TOX_NUM_PROCESSES`: Number of parallel test processes (default: auto)
- `PYTEST_TIMEOUT`: Test timeout in seconds

## Testing Workflow

1. **Create workloads**: Use fixtures to create OpenStack resources
2. **Execute operations**: Perform actions or disruptions
3. **Validate**: Check that workloads still function correctly
4. **Cleanup**: Fixtures handle resource cleanup automatically

Tests are organized under `tobiko/tests/`:
- `unit/`: Unit tests (no cloud required)
- `scenario/`: Integration tests (requires OpenStack cloud)
- `functional/`: Functional tests

## Important Notes

- When working with podified deployments, the `openshift_client` (oc) library is used extensively
- Configuration uses oslo.config pattern - all configs must be registered before use
- Fixtures are shared by default - use `get_fixture()` to retrieve existing instances
- SSH connections are managed through tobiko.shell.ssh module with connection pooling
