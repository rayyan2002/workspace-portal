-- Give the repository owner's account ROLE_ADMIN, so there is somebody who can grant it.
--
-- THE CHICKEN AND EGG THIS SOLVES. /api/admin/** is guarded by hasRole('ADMIN') and the new
-- promote endpoint is inside that guard, so an admin is required to create an admin. V16
-- retired the seeded demo accounts — correctly, their password was published in V8 — and
-- took the only ROLE_ADMIN with them. A fresh portfolio database therefore has users and no
-- way to promote any of them short of editing the database by hand.
--
-- WHY AN EMAIL AND NOT "the first user". Promoting whoever registered first is the tidier
-- rule and the wrong one here: on a database that already has accounts it hands admin to
-- whoever happened to sign up earliest, which on a shared machine is not necessarily the
-- person who owns the deployment. Naming the account is explicit about who gets it.
--
-- A NO-OP ANYWHERE ELSE. If that account does not exist — any clone but this one — the
-- INSERT selects no rows and the migration does nothing. It grants a ROLE, never a
-- password: the account must already have been registered through the ordinary sign-up
-- flow, so no credential is written into version control by this file.

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
CROSS JOIN roles r
WHERE u.email = 'rayyanayub5@gmail.com'
  AND r.name = 'ROLE_ADMIN'
ON CONFLICT DO NOTHING;
