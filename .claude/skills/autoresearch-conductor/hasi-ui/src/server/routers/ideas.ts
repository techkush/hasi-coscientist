import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

const slug = z.object({ slug: z.string().min(1) });

export const ideasRouter = router({
  list: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.ideasList(input.slug))),
  ideaMd: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.ideasIdeaMd(input.slug))),
  proposal: procedure.input(slug).query(({ input }) =>
    withConductor(() => conductor.ideasProposal(input.slug))),

  execute: procedure
    .input(slug.extend({ paperLimit: z.number().int().min(0).max(100).default(10) }))
    .mutation(({ input }) =>
      withConductor(() => conductor.ideasExecute(input.slug, input.paperLimit))),
  propose: procedure
    .input(slug.extend({ text: z.string().min(1) }))
    .mutation(({ input }) =>
      withConductor(() => conductor.ideasPropose(input.slug, input.text))),
  confirm: procedure
    .input(slug.extend({ accept: z.boolean(), force: z.boolean().optional() }))
    .mutation(({ input }) =>
      withConductor(() => conductor.ideasConfirm(input.slug, input.accept, !!input.force))),

  removeBasketFile: procedure
    .input(slug.extend({ filename: z.string().min(1) }))
    .mutation(({ input }) =>
      withConductor(() => conductor.ideasDelete(input.slug, input.filename))),
});
