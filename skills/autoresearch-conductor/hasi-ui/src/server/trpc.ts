import { initTRPC, TRPCError } from "@trpc/server";
import superjson from "superjson";
import { ConductorError } from "./conductor";

const t = initTRPC.create({
  transformer: superjson,
  errorFormatter({ shape, error }) {
    return { ...shape, data: { ...shape.data, cause: error.cause instanceof Error ? error.cause.message : undefined } };
  },
});

export const router = t.router;
export const procedure = t.procedure;

/** Wrap a thunk so ConductorError surfaces as a useful TRPCError. */
export async function withConductor<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (e instanceof ConductorError) {
      const code =
        e.status === 404 ? "NOT_FOUND" :
        e.status === 409 ? "CONFLICT" :
        e.status === 400 ? "BAD_REQUEST" :
        e.status === 0 ? "INTERNAL_SERVER_ERROR" :
        "INTERNAL_SERVER_ERROR";
      throw new TRPCError({ code, message: e.body || e.message, cause: e });
    }
    throw e;
  }
}
