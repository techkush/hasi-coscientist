import { z } from "zod";
import { router, procedure, withConductor } from "../trpc";
import { conductor } from "../conductor";

export const newProjectRouter = router({
  state: procedure.query(() => withConductor(() => conductor.newState())),
  questions: procedure.query(() => withConductor(() => conductor.newQuestions())),
  variations: procedure.query(() => withConductor(() => conductor.newVariations())),
  spec: procedure
    .input(z.object({ id: z.number().int().min(1) }))
    .query(({ input }) => withConductor(() => conductor.newSpec(input.id))),

  start: procedure
    .input(z.object({
      idea: z.string().min(3),
      name: z.string().optional(),
      domain: z.string().optional(),
    }))
    .mutation(({ input }) => withConductor(() => conductor.newStart(input))),

  answer: procedure
    .input(z.object({ answers: z.record(z.string(), z.string()) }))
    .mutation(({ input }) => withConductor(() => conductor.newAnswers(input.answers))),

  revise: procedure
    .input(z.object({ text: z.string().min(1), base_id: z.number().int().optional() }))
    .mutation(({ input }) => withConductor(() => conductor.newChange(input))),

  confirm: procedure
    .input(z.object({ id: z.number().int().min(1) }))
    .mutation(({ input }) => withConductor(() => conductor.newConfirm(input.id))),
});
