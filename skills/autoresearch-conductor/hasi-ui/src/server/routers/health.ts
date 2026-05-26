import { router, procedure } from "../trpc";
import { ConductorError, conductor } from "../conductor";

/**
 * Probe the Python conductor at startup. If this fails, every other call will
 * too — the home page surfaces this so the user doesn't get a silent "nothing
 * happens" when creating a project.
 */
export const healthRouter = router({
  conductor: procedure.query(async () => {
    try {
      await conductor.state();
      return {
        ok: true as const,
        url: process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780",
      };
    } catch (e) {
      const url = process.env.CONDUCTOR_URL ?? "http://127.0.0.1:8780";
      const reason =
        e instanceof ConductorError
          ? `${e.status === 0 ? "network unreachable" : `HTTP ${e.status}`}: ${e.body || e.message}`
          : (e as Error).message;
      return { ok: false as const, url, reason };
    }
  }),
});
