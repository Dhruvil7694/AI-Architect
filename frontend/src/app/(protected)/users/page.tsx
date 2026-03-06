export default function UsersPage() {
  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-neutral-900">My profile</h2>
        <p className="text-sm text-neutral-500">
          Basic user profile and preferences will be shown here.
        </p>
      </header>
      <div className="rounded-md border border-neutral-200 bg-white p-4 text-sm text-neutral-600">
        This page is optional and will surface per-user settings once the auth
        and user modules are wired to the backend.
      </div>
    </section>
  );
}

