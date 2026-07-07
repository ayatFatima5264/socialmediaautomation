import LegalPage from './LegalPage.jsx'
import Seo from '../../components/Seo.jsx'
import { SITE } from '../../config/site'

const SECTIONS = [
  {
    heading: '1. Introduction',
    body: [
      `This Privacy Policy explains how ${SITE.name} ("we", "us", or "our") collects, uses, shares, and protects your information when you use our website and application (the "Service"). We designed the Service to help you create and publish social media content, and we take the privacy of the data involved seriously.`,
      'By creating an account or using the Service, you agree to the practices described in this policy. If you do not agree, please do not use the Service.',
    ],
  },
  {
    heading: '2. Information We Collect',
    body: [
      'Account information: your name, email address, and password (stored in hashed form) when you register.',
      'Business profile: details you provide during onboarding — such as your business name, industry, target audience, brand voice, goals, and website — which we use to personalize AI-generated content.',
      'Content and AI prompts: the prompts you enter, the content you create or import, and the posts, captions, images, and carousels the Service generates or that you schedule and publish.',
      'Connected social accounts: when you connect a platform, we store the access tokens and basic account details needed to publish on your behalf.',
      'Usage and device data: technical information such as browser type, device, and interactions with the Service, collected to keep it secure and improve it.',
    ],
  },
  {
    heading: '3. How We Use Your Information',
    body: [
      'We use your information to provide, operate, and improve the Service; generate content personalized to your business profile; publish to your connected accounts when you instruct us to; provide support; secure our systems and prevent abuse; and communicate with you about your account and important changes.',
      'We do not sell your personal information.',
    ],
  },
  {
    heading: '4. AI Prompts and Generated Content',
    body: [
      'Your prompts and the content you generate are processed to deliver results and may be handled by third-party AI providers strictly to perform that processing. We do not use your private prompts or generated content to train our own models without your consent.',
      'You are responsible for reviewing AI-generated content before publishing it. Generated output may be inaccurate or require editing.',
    ],
  },
  {
    heading: '5. Connected Social Media Accounts',
    body: [
      'When you connect a social platform, you authorize us to access the permissions you grant (for example, publishing content). We store only the tokens and metadata needed to provide the Service.',
      'You can disconnect any account at any time from your dashboard, which revokes our access to that platform going forward.',
    ],
  },
  {
    heading: '6. Cookies and Analytics',
    body: [
      'We use essential cookies to keep you signed in and remember preferences such as your theme. With your consent where required, we may use privacy-respecting analytics to understand how the Service is used so we can improve it. You can control cookies through your browser settings.',
    ],
  },
  {
    heading: '7. How We Share Information',
    body: [
      'We share information only with service providers who help us operate the Service (such as hosting, AI processing, and payment processing), and only to the extent needed to perform their work under confidentiality obligations.',
      'We may disclose information if required by law, to protect our rights and users, or in connection with a merger or acquisition. We do not sell your data to advertisers.',
    ],
  },
  {
    heading: '8. Data Retention',
    body: [
      'We retain your information for as long as your account is active or as needed to provide the Service. You can delete your content or account at any time; we will delete or anonymize your personal data within a reasonable period, except where retention is required by law.',
    ],
  },
  {
    heading: '9. Data Security',
    body: [
      'We use industry-standard measures to protect your data in transit and at rest, including encryption and access controls. No method of transmission or storage is completely secure, but we work continuously to safeguard your information.',
    ],
  },
  {
    heading: '10. Your Rights and Choices',
    body: [
      'Depending on your location, you may have the right to access, correct, export, or delete your personal data, and to object to or restrict certain processing. You can manage most of your information directly in your settings.',
      `To exercise any right or ask a question, contact us at ${SITE.supportEmail}.`,
    ],
  },
  {
    heading: '11. International Data Transfers',
    body: [
      'Your information may be processed in countries other than your own. Where we transfer data internationally, we take steps to ensure it receives an adequate level of protection consistent with this policy.',
    ],
  },
  {
    heading: '12. Children\'s Privacy',
    body: [
      'The Service is not intended for anyone under the age of 16, and we do not knowingly collect personal information from children. If you believe a child has provided us data, please contact us and we will remove it.',
    ],
  },
  {
    heading: '13. Changes to This Policy',
    body: [
      'We may update this Privacy Policy from time to time. Material changes will be communicated through the app or by email, and the "Last updated" date above will reflect the latest revision.',
    ],
  },
  {
    heading: '14. Contact Us',
    body: [`Questions about this policy or your data? Reach us at ${SITE.supportEmail}.`],
  },
]

export default function Privacy() {
  return (
    <>
      <Seo
        title="Privacy Policy"
        description="How AutoSocial AI collects, uses, and protects your account, business profile, AI prompts, and connected social accounts."
      />
      <LegalPage title="Privacy Policy" updated="July 8, 2026" sections={SECTIONS} />
    </>
  )
}
