interface AvatarProps {
  email?: string;
  size?: number;
}

const COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f97316', '#10b981', '#3b82f6'];

function getColor(email: string): string {
  let hash = 0;
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash);
  }
  return COLORS[Math.abs(hash) % COLORS.length];
}

function getInitial(email: string): string {
  return email.charAt(0).toUpperCase();
}

export default function Avatar({ email = '', size = 32 }: AvatarProps) {
  if (!email) {
    return (
      <div
        className="rounded-full flex items-center justify-center text-white font-semibold"
        style={{ width: size, height: size, backgroundColor: '#6b7280', fontSize: size * 0.4 }}
      >
        ?
      </div>
    );
  }

  return (
    <div
      className="rounded-full flex items-center justify-center text-white font-semibold"
      style={{ width: size, height: size, backgroundColor: getColor(email), fontSize: size * 0.4 }}
      title={email}
    >
      {getInitial(email)}
    </div>
  );
}
