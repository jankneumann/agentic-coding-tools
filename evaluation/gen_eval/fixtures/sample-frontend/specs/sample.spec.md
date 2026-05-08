# Sample frontend OpenSpec scenarios

Used by the Playwright validator's e2e fixture (see
`skills/tests/playwright-validator/test_e2e_sample.py`). The scenarios
describe the click-and-assert flow exercised by
`evaluation/gen_eval/fixtures/sample-frontend/index.html`.

## ADDED Requirements

### Requirement: Login Flow

The sample frontend SHALL allow a user to log in by entering credentials
and clicking the login button. The welcome message SHALL appear with the
entered username after a successful click.

#### Scenario: User logs in successfully

- **WHEN** the user navigates to the home page
- **AND** the user fills username_field with "alice"
- **AND** the user fills password_field with "password"
- **AND** the user clicks login_button
- **THEN** welcome_message is visible
- **AND** welcome_message contains "Welcome, alice"

#### Scenario: Empty credentials keep welcome hidden

- **WHEN** the user navigates to the home page
- **AND** the user clicks login_button
- **THEN** welcome_message is hidden
