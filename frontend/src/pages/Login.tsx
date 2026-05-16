import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { setApiAuthKey } from "@/lib/apiAuth";

export function Login() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);

    try {
      if (tab === "register") {
        await api.register(username, password);
        toast.success("Registration successful. Please log in.");
        setTab("login");
        setPassword("");
      } else {
        const res = await api.login(username, password);
        setApiAuthKey(res.access_token);
        toast.success("Logged in");
        navigate("/", { replace: true });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          toast.error("Username already exists");
        } else {
          toast.error(err.message);
        }
      } else {
        toast.error("An error occurred");
      }
    } finally {
      setLoading(false);
    }
  }

  const fieldClass =
    "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20";
  const btnClass =
    "w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-xl border bg-card p-8 shadow-sm">
        <h1 className="mb-6 text-center text-xl font-semibold">Vibe Trading AI</h1>

        <div className="mb-6 flex gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            onClick={() => setTab("login")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === "login" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Login
          </button>
          <button
            type="button"
            onClick={() => setTab("register")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === "register" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              maxLength={32}
              className={fieldClass}
              placeholder="3-32 characters"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              maxLength={128}
              className={fieldClass}
              placeholder="8-128 characters"
            />
          </div>
          <button type="submit" disabled={loading} className={btnClass}>
            {loading ? "..." : tab === "login" ? "Login" : "Register"}
          </button>
        </form>
      </div>
    </div>
  );
}
