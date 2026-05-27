import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";
import { listProjects, syncProjects } from "../db";

const slug = z.object({ slug: z.string().min(1) });

export const projectsRouter = router({
  list: procedure.query(() => withConductor(async () => {
    const fresh = await syncProjects();
    return fresh;
  })),
  listCached: procedure.query(() => listProjects()),
  detail: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.project(input.slug))),
  spec: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.spec(input.slug))),
  results: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.results(input.slug))),
  task: procedure.query(() => withConductor(() => conductor.task())),
});
