/* The whole renderer test bundle, in one entry point.
 *
 * `npm run test` compiles this with the esbuild that already ships inside Vite and runs it on node — no
 * test runner, no new dependency. Each imported file asserts and throws on failure, so a non-zero exit is
 * the whole reporting mechanism.
 */

import "./core/worlds.test";
import "./core/core.test";
import "./core/nav.test";
import "./protocol.test";
