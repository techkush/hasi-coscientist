import { fetchRequestHandler } from "@trpc/server/adapters/fetch";
import { appRouter } from "@/server/router";

const handler = (req: Request) =>
  fetchRequestHandler({
    endpoint: "/api/trpc",
    req,
    router: appRouter,
    createContext: () => ({}),
    onError({ error, path }) {
      if (error.code === "INTERNAL_SERVER_ERROR") {
        console.error(`[trpc:${path}]`, error.message);
      }
    },
  });

export { handler as GET, handler as POST };
