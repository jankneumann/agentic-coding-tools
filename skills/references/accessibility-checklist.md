# Accessibility Checklist (WCAG 2.1 AA)

Cited by `frontend-ui-engineering`, `code-review-and-quality`, and any UI work. The minimum bar for shippable UI; no feature is "done" until it passes.

## Keyboard

- [ ] Every interactive element is reachable with `Tab` in a logical order
- [ ] Focus is visible (custom focus rings are fine — invisible is not)
- [ ] `Esc` closes modals; `Enter`/`Space` activates buttons; arrow keys navigate within composite widgets (menu, listbox, tabs)
- [ ] No keyboard traps (`Tab` can always exit a region)
- [ ] Skip-to-main-content link is the first focusable element on every page

## Screen reader / ARIA

- [ ] Every form control has a programmatic label (`<label for>`, `aria-label`, or `aria-labelledby`)
- [ ] Decorative icons have `aria-hidden="true"`; informative icons have `aria-label`
- [ ] Buttons that toggle state expose `aria-pressed` / `aria-expanded`
- [ ] Live regions (`role="status"`, `role="alert"`) used for dynamic content updates
- [ ] Landmark regions present (`<header>`, `<nav>`, `<main>`, `<footer>`) and labeled if duplicated
- [ ] Custom widgets follow ARIA Authoring Practices patterns — don't invent your own role/state semantics

## Color & contrast

- [ ] Text contrast ≥ 4.5:1 against its background (≥ 3:1 for ≥18pt or ≥14pt bold)
- [ ] Non-text UI (icons, focus rings, form borders) ≥ 3:1
- [ ] Color is not the *only* signal for state — pair red/green with icons or text
- [ ] Tested in dark mode if the UI supports it

## Forms

- [ ] Required fields marked both visually and programmatically (`required`, `aria-required="true"`)
- [ ] Error messages associated with fields (`aria-describedby`) and announced (`aria-live="polite"`)
- [ ] Errors say *what's wrong AND how to fix it*, not just "Invalid"
- [ ] Field grouping uses `<fieldset>` + `<legend>` for related controls
- [ ] Autofill hints set (`autocomplete="email"`, `"current-password"`, etc.)

## Motion & timing

- [ ] Animations respect `prefers-reduced-motion`
- [ ] No auto-playing video/audio with sound
- [ ] Time limits are adjustable, extendable, or removable (or warn the user)
- [ ] Carousels can be paused
- [ ] No content flashes ≥3 times per second

## Images & media

- [ ] Every `<img>` has `alt` (empty `alt=""` for decorative; descriptive for informative)
- [ ] Complex images (charts, diagrams) have a long description nearby or via `aria-describedby`
- [ ] Videos have captions; audio has transcripts

## Structure

- [ ] One `<h1>` per page; heading levels don't skip (`<h2>` then `<h4>` is wrong)
- [ ] Lists use `<ul>`/`<ol>`, tables use `<table>` + `<th>` with `scope`
- [ ] Page has a `<title>` that's distinct and describes the page

## Mobile / touch

- [ ] Tap targets ≥ 44×44 CSS pixels
- [ ] Pinch-zoom not disabled (`<meta name="viewport">` does not have `user-scalable=no`)
- [ ] Content reflows at 320px wide without horizontal scroll
- [ ] Hover-only interactions have a touch-friendly equivalent

## Empty / loading / error states

- [ ] Loading state announced to screen readers (`aria-busy="true"` or `aria-live`)
- [ ] Empty state explains what to do next, not just "No data"
- [ ] Error state explains what failed and offers a retry or alternative

## Verification

- [ ] Axe DevTools or Lighthouse a11y score ≥ 95
- [ ] Manual screen reader pass (VoiceOver / NVDA) for the primary user flow
- [ ] Manual keyboard-only pass for the primary user flow
- [ ] Color picker/contrast tool used to verify edge-case combinations
