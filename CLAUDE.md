# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant Red Energy Integration project. The repository is currently in its initial state with only basic documentation files (README.md and LICENSE).

## Current State

The repository contains:
- README.md: Basic project description
- LICENSE: MIT license
- This repository appears to be a fresh project setup for creating a Home Assistant integration for Red Energy (Australian energy provider)

## Implementation Plan Status

**Current Stage**: Stage 1 - COMPLETED ✅

### Completed Stages
- Planning and research phase completed
- **Stage 1**: Project Foundation & Core Structure ✅
  - ✅ Set up integration directory structure
  - ✅ Create manifest.json  
  - ✅ Implement const.py
  - ✅ Create __init__.py
  - ✅ Set up test framework
  - ✅ Verify integration loads (tests pass)

### Ready for Stage 2
Authentication & Configuration Flow (UI-based setup) - awaiting user approval to proceed

## Development Commands

Testing:
```bash
pytest tests/ -v
```

## Architecture Overview

This integration will implement:
- **UI-First Configuration**: All setup via Home Assistant's configuration flow UI
- Authentication using existing Red Energy API patterns (username, password, client_id)
- Multi-account support through Home Assistant config entries
- Account/service selection (electricity, gas, or both) via options flow UI
- Polling-based data updates using DataUpdateCoordinator
- Sensor entities for usage, cost, and billing data
- Support for both electricity and gas services

## Configuration Flow Design

**Initial Setup Flow (config_flow.py)**:
1. User credentials input (username, password, client_id)
2. Credential validation with Red Energy API
3. Account discovery and selection
4. Service type selection (electricity, gas, or both)
5. Final confirmation and integration creation

**Options Flow** (for post-setup changes):
- Modify account selections
- Change service types
- Update polling intervals
- Credential updates

## Stage-Based Development

The implementation follows an 8-stage plan where each stage must be completed and user-approved before proceeding. Each stage builds upon the previous to create a production-ready Home Assistant integration with comprehensive UI-based configuration.