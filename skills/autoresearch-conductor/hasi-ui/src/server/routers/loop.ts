import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

const slug = z.object({ slug: z.string().min(1) });

export const loopRouter = router({
  state: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.runState(input.slug))),
  log: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.runLog(input.slug))),
  start: procedure.input(slug).mutation(({ input }) =>
    withConductor(() => conductor.loopStart(input.slug))),
  /**
   * Stop is best-effort: it writes loop_stop.json which the bridge polls
   * between iterations, and also asks the conductor to set run_state to
   * "stopping". The Python side will let the current iteration finish, then
   * unwind. The button on the UI should remain showing "Stop" until the loop
   * actually exits (we detect that via task.active falling).
   */
  stop: procedure.input(slug).mutation(({ input }) =>
    withConductor(() => conductor.loopStop(input.slug))),
});
