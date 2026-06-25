// UI component types and rendering utilities

export interface User {
  id: number;
  username: string;
  email?: string;
}

export interface UserCardProps {
  user: User;
  showEmail: boolean;
}

export function renderUser(user: User): string {
  return `[${user.id}] ${user.username}`;
}

export function renderUserCard(props: UserCardProps): string {
  const base = renderUser(props.user);
  if (props.showEmail && props.user.email) {
    return `${base} <${props.user.email}>`;
  }
  return base;
}

export async function fetchUser(id: number): Promise<User> {
  const response = await fetch(`/api/users/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch user ${id}`);
  }
  return response.json() as Promise<User>;
}
