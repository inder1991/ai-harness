// v1.3.0 S17 (S-CV3) — multi-dot stems like `MyComponent.test.tsx`
// must NOT fire Q18.frontend-component-pascal-case. Pre-v1.3.0 the
// regex required `^[A-Z][A-Za-z0-9]*$` against the whole stem,
// which failed because of the embedded `.test`.
export const MyComponent = () => <div>x</div>;
