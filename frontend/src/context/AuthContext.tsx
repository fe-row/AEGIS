"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { getMe, logout, hasSession } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  logout: () => { },
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Fetch user on mount — HttpOnly cookie is sent automatically
  useEffect(() => {
    if (!hasSession()) {
      setLoading(false);
      return;
    }

    getMe()
      .then((u) => {
        setUser(u);
        setLoading(false);
      })
      .catch(() => {
        logout();
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redirect guard: push to login if no session and not on login page
  useEffect(() => {
    if (!hasSession() && !loading && pathname !== "/") {
      router.push("/");
    }
  }, [pathname, router, loading]);

  return (
    <AuthContext.Provider value={{ user, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}