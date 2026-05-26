import { router } from "./trpc";
import { projectsRouter } from "./routers/projects";
import { newProjectRouter } from "./routers/newProject";
import { generateRouter } from "./routers/generate";
import { setupRouter } from "./routers/setup";
import { ideasRouter } from "./routers/ideas";
import { loopRouter } from "./routers/loop";
import { analyzeRouter } from "./routers/analyze";
import { systemRouter } from "./routers/system";
import { healthRouter } from "./routers/health";

export const appRouter = router({
  projects: projectsRouter,
  newProject: newProjectRouter,
  generate: generateRouter,
  setup: setupRouter,
  ideas: ideasRouter,
  loop: loopRouter,
  analyze: analyzeRouter,
  system: systemRouter,
  health: healthRouter,
});

export type AppRouter = typeof appRouter;
