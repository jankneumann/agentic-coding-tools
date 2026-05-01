# Testing Patterns

Cited by `test-driven-development`, `debugging-and-error-recovery`, `code-review-and-quality`, and any skill that authors or evaluates tests.

## The test pyramid (Cohn's pyramid, modernized)

Roughly **80% unit / 15% integration / 5% E2E** by count. Inverted pyramids (lots of E2E, few unit) are slow, flaky, and produce expensive maintenance burden.

| Layer | What it tests | Speed | Stability | Owns |
|---|---|---|---|---|
| Unit | One function/class in isolation | <10ms each | Very stable | Most logic, edge cases |
| Integration | A vertical slice (DB + service + handler) | 100ms–1s each | Stable | Wiring, contracts, real-DB queries |
| E2E | A full user journey through the deployed system | 1s–30s each | Flaky-prone | One critical-path-per-feature, no more |

## Naming

Test names describe the behavior, not the function called.

- ✅ `test_user_cannot_delete_another_users_post`
- ❌ `test_delete_post`
- ✅ `test_login_returns_401_when_password_is_wrong`
- ❌ `test_login_2`

## Arrange-Act-Assert (AAA)

Three visually-distinct sections, blank lines between:

```python
def test_user_can_log_in_with_valid_credentials():
    # Arrange
    user = create_user(email="alice@example.com", password="correct horse")

    # Act
    response = client.post("/login", json={"email": user.email, "password": "correct horse"})

    # Assert
    assert response.status_code == 200
    assert "session_token" in response.cookies
```

Reading the test should take ~5 seconds.

## DAMP > DRY (in tests)

**D**escriptive **A**nd **M**eaningful **P**hrases beats **D**on't **R**epeat **Y**ourself when reading. Inline a small constant rather than chasing a fixture three files away.

- ✅ Inline `email="alice@example.com"` in two tests; the duplication is readable.
- ❌ A `@pytest.fixture` named `user` that secretly varies based on test ID.

## One assertion per concept

You can have multiple `assert` statements, but they should all support **one claim**. If your test has comments labeling unrelated assertion groups, split it.

## State, not interactions (mostly)

Prefer asserting on observable state (return value, side-effect on DB, file written) over assertions on which methods were called.

- ✅ `assert User.objects.filter(email="alice@...").exists()`
- ❌ `mock_user_repo.save.assert_called_once_with(...)` (couples test to implementation)

Mock-heavy interaction-tests are valid for adapter/wrapper layers where the *only* observable behavior is the call, but they're a smell elsewhere.

## The "Beyonce Rule"

> If you liked it, put a test on it.

Any behavior you intend to preserve gets a test. This is the rule that catches "we relied on that subtle ordering" bugs at refactor time.

## The "Prove-It Pattern" (for bugs)

Every bug fix starts with a failing test that *would have caught the bug*. The fix lands when the test passes. The test stays in the suite forever as a regression guard.

```text
1. Reproduce the bug locally.
2. Write a test that asserts the correct behavior. Run it. It MUST fail.
3. Implement the fix.
4. Run the test. It MUST pass.
5. Commit test and fix together; reference the bug in the commit body.
```

## RED → GREEN → REFACTOR

Classic TDD cycle:

1. **RED**: Write the smallest failing test for the next behavior.
2. **GREEN**: Write the simplest code that makes it pass — even if it's ugly.
3. **REFACTOR**: With the safety net, clean up. Run tests after each change.

Each cycle is small enough to fit in your head.

## Anti-patterns

- **Tests that always pass.** A test that doesn't fail on broken code is an empty assertion. Mutate the implementation to confirm the test catches it.
- **Snapshot tests as the only assertion.** Snapshot drift trains reviewers to rubber-stamp; couple snapshots with at least one explicit behavior assertion.
- **`time.sleep` for synchronization.** Use the real signal (`wait_until`, `pytest-asyncio`, condition variables). Sleeps make tests flaky AND slow.
- **Tests that depend on test order.** Each test must set up its own state. If `test_b` requires `test_a` to have run, fold them into one test or fix the fixture.
- **Mocking the system under test.** If you mock the thing you're testing, you've tested the mock.
- **Testing the framework.** Don't write a test that asserts `[].append(1) == [1]`. Test *your* code.

## Backend Python (pytest)

```python
# Parametrize for combinatorial coverage
@pytest.mark.parametrize("input,expected", [
    ("alice@example.com", True),
    ("alice@", False),
    ("", False),
    ("a@b.c" * 100, False),  # length limit
])
def test_is_valid_email(input, expected):
    assert is_valid_email(input) == expected

# Use fixtures for non-trivial setup
@pytest.fixture
def authenticated_client(client, db):
    user = create_user()
    client.force_login(user)
    return client

# Run a single test by name during debugging
# pytest tests/ -k "test_is_valid_email and length"
```

## Frontend (Jest / Vitest)

```typescript
import { render, screen, userEvent } from '@testing-library/react';

test('clicking submit posts the form data', async () => {
  const onSubmit = vi.fn();
  render(<LoginForm onSubmit={onSubmit} />);

  await userEvent.type(screen.getByLabelText(/email/i), 'alice@example.com');
  await userEvent.type(screen.getByLabelText(/password/i), 'hunter2');
  await userEvent.click(screen.getByRole('button', { name: /log in/i }));

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'alice@example.com',
    password: 'hunter2',
  });
});
```

Use queries by accessible role (`getByRole`) over `getByTestId` — it asserts the UI is also accessible.

## Browser E2E (Playwright)

```typescript
test('user can log in', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email').fill('alice@example.com');
  await page.getByLabel('Password').fill('hunter2');
  await page.getByRole('button', { name: 'Log in' }).click();

  await expect(page).toHaveURL('/dashboard');
  await expect(page.getByText('Welcome, Alice')).toBeVisible();
});
```

Avoid `page.waitForTimeout(...)`. Use Playwright's auto-waiting or explicit `expect(...).toBeVisible({ timeout })`.
