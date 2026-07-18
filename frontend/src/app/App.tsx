import { RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { authService } from "../api/runtime";
import { AuthProvider } from "../auth/AuthProvider";
import { router } from "./routes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={authService}>
        <RouterProvider router={router} />
        <Toaster richColors position="top-right" closeButton />
      </AuthProvider>
    </QueryClientProvider>
  );
}
