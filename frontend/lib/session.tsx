'use client';

// Who is looking at this page, and what that lets them do.
//
// One question is asked once, on load: `GET /api/auth/me`. Every screen that cares reads
// the answer out of context instead of asking again, so a page cannot show an "Edit"
// button that the API is going to refuse. The session itself is a cookie the browser
// holds; nothing here stores a token, because there is no token to store.
//
// `unreachable` is a state of its own and not an error: with the API down, the Nav says
// "Service offline" once and every signed-in affordance quietly stays out of the way.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api } from './api';
import type { PersistenceState, Session } from './types';

export type SessionStatus = 'checking' | 'anonymous' | 'signed_in' | 'unreachable';

export interface SessionState {
  status: SessionStatus;
  session: Session | null;
  persistence: PersistenceState | null;
  error: string | null;
}

interface SessionValue extends SessionState {
  /** Re-read `/api/auth/me`: after a sign-in, after a tenant switch, after a save. */
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Whether this person's role may write. Viewers and signed-out visitors read. */
  canWrite: boolean;
  canManageMembers: boolean;
}

const INITIAL: SessionState = { status: 'checking', session: null, persistence: null, error: null };

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>(INITIAL);

  const load = useCallback(async () => {
    try {
      const body = await api.session();
      setState({
        status: body.signed_in && body.session ? 'signed_in' : 'anonymous',
        session: body.session ?? null,
        persistence: body.persistence ?? null,
        error: null,
      });
    } catch (err) {
      setState((previous) => ({
        ...previous,
        status: 'unreachable',
        error: err instanceof Error ? err.message : 'Symbio could not check whether anyone is signed in.',
      }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const signOut = useCallback(async () => {
    try {
      await api.signOut();
    } catch {
      /* a session the server could not revoke is still a session this page forgets */
    }
    await load();
  }, [load]);

  const value = useMemo<SessionValue>(
    () => ({
      ...state,
      refresh: load,
      signOut,
      canWrite: Boolean(state.session?.can_write),
      canManageMembers: Boolean(state.session?.can_manage_members),
    }),
    [state, load, signOut]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession needs to be used inside <SessionProvider>.');
  return value;
}
