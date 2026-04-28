// v1.3.0 S17 (S-CV1) — `from "./relative"` (single dot) must NOT
// fire Q18.no-dotdot-import-frontend. The rule only bans `../..`
// style. Pre-v1.3.0 the regex `\.\.?/` matched both.
import { foo } from "./sibling";

export const X = () => foo;
