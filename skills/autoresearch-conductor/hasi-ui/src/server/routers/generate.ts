import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

const slug = z.object({ slug: z.string().min(1) });

export const generateRouter = router({
  plan: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.genPlan(input.slug))),
  manifest: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.genManifest(input.slug))),
  file: procedure
    .input(slug.extend({ path: z.string().min(1) }))
    .query(({ input }) => withConductor(() => conductor.genFile(input.slug, input.path))),
  execute: procedure.input(slug).mutation(({ input }) =>
    withConductor(() => conductor.genExecute(input.slug))),
  chat: procedure
    .input(slug.extend({ text: z.string().min(1) }))
    .mutation(({ input }) => withConductor(() => conductor.genChat(input.slug, input.text))),
  chatProposal: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.genChatProposal(input.slug))),
  chatConfirm: procedure
    .input(slug.extend({ accept: z.boolean(), force: z.boolean().optional() }))
    .mutation(({ input }) =>
      withConductor(() => conductor.genChatConfirm(input.slug, input.accept, !!input.force))),
  done: procedure.input(slug).mutation(({ input }) =>
    withConductor(() => conductor.genDone(input.slug))),
});
