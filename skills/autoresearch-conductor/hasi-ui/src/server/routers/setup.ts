import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

const slug = z.object({ slug: z.string().min(1) });

export const setupRouter = router({
  result: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.setupResult(input.slug))),
  execute: procedure.input(slug).mutation(({ input }) =>
    withConductor(() => conductor.setupExecute(input.slug))),
});
