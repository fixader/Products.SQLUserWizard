# SQLUserWizard 0.2.0b1

Release date: 2026-09-26. This is the first beta release for controlled evaluation.

The release fixes the Zope 6 ZMI object listing for folders containing generated
SQLUserWizard methods. Version 0.2.0a2 denied `Use Database Methods` to every
role. That blocked direct public execution, but also prevented the standard ZMI
folder template from traversing those objects for a Manager.

Generated Z SQL Methods now grant that permission only to `Manager`, with
acquisition disabled. Anonymous and ordinary users remain unable to call the raw
methods. Running **Install / Repair** updates existing generated methods.

This release also adds the UI work verified in the chapter 4 lab:

- a Manager profile-field editor supporting validated text, email, telephone,
  URL, textarea, checkbox and select fields, including address and descriptive
  user-type fields when an application wants them;
- explicit allowlisted JSON storage for additional values in the managed SQL
  profile row;
- a shared static stylesheet and cleaner user, role and profile layouts;
- invitation forms, wrappers, narrow proxy-role mappings, local CSS and Manager
  notes generated automatically when invitations are enabled;
- optional automatic invitation delivery using only a MailHost stored directly
  in the generated `invitations` folder, with fixed sender, subject and public
  invitation URL configured through SQL User Admin;
- append-only delivery events in the Zope server log without invitation tokens,
  complete URLs, message bodies or SMTP credentials;
- a Manager-controlled policy that makes TOTP enrollment optional or required
  for newly invited accounts;
- a simpler public form that uses one login name as the default stable user ID,
  plus a proper account-created page leading to normal login;
- a clearer provisioning icon and a profile partial that renders safely in ZMI;
- profile/logout links hidden from anonymous visitors on the login screen.

Invitation creation remains Manager-only. Public inspection and completion use
only the dedicated `InvitationInspector` and `InvitationCompleter` proxy roles.
Generated forms retain POST and CSRF requirements. SQLUserWizard does not create
a MailHost or bundle a mail service. When a Manager adds and configures a local
MailHost, the protected controller reads that object's SMTP settings and sends
only the fixed invitation message. MailHost objects inherited from a parent are
ignored deliberately.

The complete local suite passes on the release source. The candidate was installed on the
Plone 6.2.2 / Zope 6.2 chapter lab, where profile-field SQL storage, Manager
field creation/removal, invitation object repair, public/Manager permission
boundaries, optional TOTP policy, SMTP STARTTLS authentication, real invitation
delivery, ordinary login, profile lookup and the anonymous login page were verified.
