# Failure Analysis and Self-Healing Architecture

These diagrams describe the implemented system. They use Mermaid and can be
rendered in GitHub, Mermaid Live Editor, or VS Code with a Mermaid extension.

## 1. System Architecture

```mermaid
flowchart TB
    User[Developer / QA User]

    subgraph Frontend[Next.js Frontend]
        Submit[Submit Failure Page]
        Results[Analysis and Action Results]
        History[Repair History / Audit Page]
    end

    subgraph Backend[FastAPI Backend]
        Analyze[POST /analyze/]
        RepairAPI[Repair API\n/plan, /publish, /history]
        GitHubMetadata[GitHub Actions Metadata Service]
        Classifier[Root Cause Service\nNine-class classifier]
        Evidence[Evidence Extraction\nand Secret Redaction]
        Policy[Root Cause Action Policy Matrix]
        Eligibility[Controlled Repair Eligibility]
        AuditServices[Notification and Action\nAudit Services]
        RepairClient[Repair Agent Client]
    end

    subgraph RepairAgent[Repair Agent Service]
        PlanAPI[POST /plan]
        Planner[Read-Only Repair Planner]
        PublishAPI[POST /publish]
        Publisher[Controlled Publisher]
        ReadBroker[Read-Only MCP Broker\nExact repository + failed SHA]
        WriteBroker[Publish MCP Broker\nApproved files only]
        OpenRouter[OpenRouter Provider\nStructured output, no tools]
    end

    subgraph External[External Systems]
        GitHubREST[GitHub REST API\nWorkflow run metadata]
        GitHubMCP[Official GitHub MCP]
        GitHubRepo[GitHub Repository\nActions, branches, draft PRs]
    end

    subgraph Storage[Application Database]
        CoreTables[(Failures, Healing, Flaky, Notifications)]
        RepairTables[(Repair Attempts and Publish Audits)]
        ActionTables[(Test Script and Root Cause Action Audits)]
    end

    Model[(best_9class_root_cause_model.joblib)]

    User --> Submit
    Submit --> Analyze
    Analyze --> GitHubMetadata
    GitHubMetadata --> GitHubREST
    GitHubREST --> GitHubMetadata
    Analyze --> Evidence
    Analyze --> Classifier
    Model --> Classifier
    Classifier --> Policy
    Evidence --> Eligibility
    Policy --> Eligibility

    Analyze --> CoreTables
    Analyze --> RepairTables
    Analyze --> AuditServices
    AuditServices --> ActionTables
    Analyze --> Results

    Policy -->|application_defect only| Eligibility
    Eligibility -->|explicit Start Controlled Repair| RepairAPI
    RepairAPI --> RepairClient
    RepairClient --> PlanAPI
    PlanAPI --> Planner
    Planner --> ReadBroker
    ReadBroker -->|read exact failed SHA| GitHubMCP
    GitHubMCP --> GitHubRepo
    Planner --> OpenRouter
    OpenRouter --> Planner
    Planner -->|bounded proposal| RepairClient
    RepairClient --> RepairAPI
    RepairAPI --> RepairTables

    RepairAPI -->|explicit Create Repair Branch| PublishAPI
    PublishAPI --> Publisher
    Publisher --> WriteBroker
    WriteBroker -->|auto-heal branch, one commit, draft PR| GitHubMCP
    Publisher -->|never merge| RepairClient

    Policy -->|test_script_issue| AuditServices
    Policy -->|all other non-application classes| AuditServices
    AuditServices -. no repair-agent or GitHub writes .-> ActionTables

    History --> RepairAPI
    RepairAPI --> RepairTables
    RepairAPI --> ActionTables
    RepairAPI --> History
    Results --> User
    History --> User
```

### Root-Cause Routing

```mermaid
flowchart LR
    RC{Predicted root cause}
    App[application_defect]
    Test[test_script_issue]
    Other[Seven remaining classes]

    Controlled[Controlled proposal and draft PR\nUser confirmation required]
    TestNotify[Forward to Test Script\nGeneration Module]
    SafeAudit[Diagnostic / notification /\nmanual-triage audit]
    NoWrites[No repair agent\nNo GitHub writes]

    RC --> App --> Controlled
    RC --> Test --> TestNotify --> NoWrites
    RC --> Other --> SafeAudit --> NoWrites
```

## 2. Entity-Relationship Diagram

The application currently links records through logical identifiers. The ORM
models do not declare database-level foreign-key constraints for these links.

```mermaid
erDiagram
    FAILURES {
        int id PK
        string test_id UK
        string test_name
        string pipeline
        string status
        string root_cause
        string confidence
        string healing
        text logs "sanitized"
        text stack_trace "bounded and sanitized"
        text recommendation
        boolean developer_alert
        datetime created_at
    }

    HEALING_ACTIONS {
        int id PK
        string healing_id UK
        string failure_test_id "logical reference"
        string test_name
        string repair_type
        string old_value
        string new_value
        string status
    }

    FLAKY_TESTS {
        int id PK
        string test_code UK "logical failure reference"
        string test_name
        string instability_score
        string recent_pattern
        string risk_level
    }

    NOTIFICATIONS {
        int id PK
        string failure_test_id "logical reference"
        string test_name
        string root_cause
        text message
        string target
    }

    REPAIR_ATTEMPTS {
        int id PK
        string attempt_id UK
        string failure_test_id "logical reference"
        string status
        string mode
        boolean eligible
        string eligibility_code
        text eligibility_reason
        string predicted_root_cause
        float confidence
        string decision_source
        string selected_action
        string repository_owner
        string repository_name
        bigint run_id
        string head_sha
        string head_branch
        string default_branch
        string error_type
        text error_message "application repair only"
        string candidate_file
        int candidate_line
        string log_content_sha256
        text sanitized_log_excerpt "application repair only"
        json inspected_files
        json repair_plan "bounded proposal"
        string provider_model
        boolean github_changes_made
        text failure_reason
        datetime created_at
        datetime updated_at
    }

    REPAIR_PUBLISH_AUDITS {
        int id PK
        string attempt_id UK "logical reference"
        string correlation_id
        string repository
        string base_sha
        string failed_branch
        string repair_branch
        string commit_sha
        int draft_pr_number
        text draft_pr_url
        string publish_status
        string validation_status
        json changed_files
        json safety_check_results
        string error_code
        boolean github_changes_made
        datetime created_at
        datetime updated_at
    }

    TEST_SCRIPT_NOTIFICATION_AUDITS {
        int id PK
        string notification_id UK
        string attempt_id UK "logical reference"
        string root_cause
        float confidence
        string repository
        string failed_branch
        string failed_sha
        bigint run_id
        text run_url
        string target_module
        text message
        string status
        datetime created_at
    }

    ROOT_CAUSE_ACTION_AUDITS {
        int id PK
        string audit_id UK
        string attempt_id UK "logical reference"
        string root_cause
        float confidence
        string repository
        string failed_branch
        string failed_sha
        text run_url
        string automation_level
        boolean notification_required
        string target_team_or_module
        text recommended_action
        json validation_guidance
        string history_status
        boolean github_changes_made
        datetime created_at
    }

    FAILURES ||--o{ HEALING_ACTIONS : "test_id = failure_test_id"
    FAILURES ||--o| FLAKY_TESTS : "test_id = test_code"
    FAILURES ||--o{ NOTIFICATIONS : "test_id = failure_test_id"
    FAILURES ||--o| REPAIR_ATTEMPTS : "test_id = failure_test_id"
    REPAIR_ATTEMPTS ||--o| REPAIR_PUBLISH_AUDITS : "attempt_id"
    REPAIR_ATTEMPTS ||--o| TEST_SCRIPT_NOTIFICATION_AUDITS : "attempt_id"
    REPAIR_ATTEMPTS ||--o| ROOT_CAUSE_ACTION_AUDITS : "attempt_id"
```

## 3. Database Mapping Diagram

```mermaid
flowchart LR
    subgraph Inputs[Domain Events]
        Analysis[Failure analysis completed]
        AppPlan[Application repair planned]
        AppPublish[Draft PR publishing attempted]
        TestRoute[Test script issue forwarded]
        SafeRoute[Other root cause routed]
        Flaky[Flaky test detected]
        Alert[General developer alert]
    end

    subgraph Tables[Database Tables]
        F[(failures)]
        H[(healing_actions)]
        FT[(flaky_tests)]
        N[(notifications)]
        RA[(repair_attempts)]
        RPA[(repair_publish_audits)]
        TSN[(test_script_notification_audits)]
        RCA[(root_cause_action_audits)]
    end

    subgraph ReadModels[API Read Models]
        FailureAPI[/failures and dashboard/]
        HealingAPI[/healing/]
        NotificationAPI[/notifications/]
        RepairAPI[/api/repairs/:attempt_id/]
        HistoryAPI[/api/repairs/history/]
    end

    Analysis --> F
    Analysis --> H
    Analysis --> RA
    Flaky --> FT
    Alert --> N
    AppPlan --> RA
    AppPublish --> RPA
    TestRoute --> TSN
    SafeRoute --> RCA

    F --> FailureAPI
    FT --> FailureAPI
    H --> HealingAPI
    N --> NotificationAPI
    RA --> RepairAPI
    RPA --> RepairAPI

    RA --> HistoryAPI
    RPA --> HistoryAPI
    TSN --> HistoryAPI
    RCA --> HistoryAPI

    HistoryAPI --> SafeProjection[Safe history projection\nNo logs, excerpts, plans, prompts,\ncredentials, or raw provider responses]
```

## Security Boundaries Shown in the Diagrams

- Raw uploaded logs are processed temporarily; only bounded sanitized evidence
  and hashes are retained where required.
- Only `application_defect` can reach repair planning and publishing.
- Planning uses GitHub MCP read tools pinned to the verified repository and exact
  failed SHA.
- Publishing uses a separate write token and an `auto-heal/...` branch.
- Publishing creates one commit and one draft PR; merge tools are not exposed.
- Every non-application root cause is restricted to notification, diagnostic,
  recommendation, or manual-triage audit records with `github_changes_made=false`.
- Repair History is a safe projection and excludes logs, source code, repair-plan
  JSON, prompts, secrets, tokens, and raw MCP/OpenRouter responses.
