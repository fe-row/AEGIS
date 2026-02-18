"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, register } from "@/lib/api";
import { Shield, Eye, EyeOff } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPass, setShowPass] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isLogin) {
        await login(email, password);
      } else {
        await register(email, password, fullName, org);
        await login(email, password);
      }
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-950 via-gray-900 to-aegis-900 p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-aegis-600/20 border border-aegis-500/30 mb-4">
            <Shield className="w-8 h-8 text-aegis-500" />
          </div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-aegis-200 to-aegis-500 bg-clip-text text-transparent">
            AEGIS
          </h1>
          <p className="text-gray-400 mt-1 text-sm">Agentic Identity & Access Management</p>
        </div>

        {/* Form Card */}
        <div className="bg-gray-900/80 backdrop-blur border border-gray-800 rounded-2xl p-8 shadow-2xl">
          <div className="flex mb-6 bg-gray-800 rounded-lg p-1">
            <button
              onClick={() => setIsLogin(true)}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition ${
                isLogin ? "bg-aegis-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => setIsLogin(false)}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition ${
                !isLogin ? "bg-aegis-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {!isLogin && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Full Name</label>
                  <input
                    type="text" value={fullName} onChange={(e) => setFullName(e.target.value)}
                    required={!isLogin}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                             focus:outline-none focus:border-aegis-500 focus:ring-1 focus:ring-aegis-500 transition"
                    placeholder="Jane Doe"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Organization</label>
                  <input
                    type="text" value={org} onChange={(e) => setOrg(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                             focus:outline-none focus:border-aegis-500 focus:ring-1 focus:ring-aegis-500 transition"
                    placeholder="Acme Corp"
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Email</label>
              <input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
                         focus:outline-none focus:border-aegis-500 focus:ring-1 focus:ring-aegis-500 transition"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
              <div className="relative">
                <input
                  type={showPass ? "text" : "password"} value={password}
                  onChange={(e) => setPassword(e.target.value)} required minLength={8}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 pr-10 text-sm
                           focus:outline-none focus:border-aegis-500 focus:ring-1 focus:ring-aegis-500 transition"
                  placeholder="••••••••"
                />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-sm">
                {error}
              </div>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full bg-aegis-600 hover:bg-aegis-700 disabled:opacity-50 text-white
                       font-medium py-2.5 rounded-lg transition-all duration-200 text-sm mt-2"
            >
              {loading ? "Processing..." : isLogin ? "Sign In" : "Create Account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}