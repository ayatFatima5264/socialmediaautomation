import LegalPage from './LegalPage.jsx'
import Seo from '../../components/Seo.jsx'
import { SITE } from '../../config/site'

const SECTIONS = [
  {
    heading: '1. Acceptance of Terms',
    body: [
      `These Terms of Service ("Terms") govern your access to and use of ${SITE.name} (the "Service"). By creating an account or using the Service, you agree to these Terms. If you do not agree, do not use the Service.`,
    ],
  },
  {
    heading: '2. The Service',
    body: [
      'AutoSocial AI provides tools to generate, design, schedule, and publish social media content using artificial intelligence. We may add, change, or remove features over time to improve the Service.',
    ],
  },
  {
    heading: '3. Eligibility and Accounts',
    body: [
      'You must be at least 16 years old and able to form a binding contract to use the Service. You are responsible for providing accurate registration information and keeping it up to date.',
      'You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account. Notify us promptly of any unauthorized use.',
    ],
  },
  {
    heading: '4. User Responsibilities',
    body: [
      'You are responsible for the content you create, schedule, and publish through the Service, and for ensuring you have the rights to use any material you upload or import.',
      'You agree to comply with these Terms, all applicable laws, and the terms and policies of any social platform you connect.',
    ],
  },
  {
    heading: '5. Acceptable Use',
    body: [
      'You agree not to use the Service to create or distribute content that is unlawful, hateful, harassing, deceptive, infringing, or otherwise harmful; to spam or engage in inauthentic or automated behavior that violates a platform\'s rules; to attempt to disrupt, reverse engineer, or gain unauthorized access to the Service; or to misuse AI features to generate prohibited or misleading content.',
      'We may suspend or limit access to protect the Service and our users if we reasonably believe these rules are being broken.',
    ],
  },
  {
    heading: '6. Connected Social Accounts',
    body: [
      'When you connect a social media account, you authorize us to access the permissions you grant and to publish content on your behalf as you direct. You remain responsible for what is published to your accounts through the Service.',
      'You can disconnect an account at any time, which revokes our access to that platform going forward. Your use of each platform remains subject to that platform\'s own terms.',
    ],
  },
  {
    heading: '7. AI-Generated Content',
    body: [
      'The Service uses AI to produce suggestions and content. AI output can be inaccurate, incomplete, or unsuitable, and may resemble content generated for others. You are responsible for reviewing, editing, and approving all content before it is published.',
      'To the extent permitted by law, you own the content you create with the Service, subject to your compliance with these Terms. AutoSocial AI is not responsible for content you choose to publish.',
    ],
  },
  {
    heading: '8. Subscriptions and Billing',
    body: [
      'Paid plans are billed in advance on a recurring basis. You may cancel at any time; cancellation takes effect at the end of the current billing period. Fees are non-refundable except where required by law. We may change pricing with reasonable notice.',
    ],
  },
  {
    heading: '9. Intellectual Property',
    body: [
      'The Service, including its software, design, branding, and content we provide, is owned by AutoSocial AI and protected by intellectual property laws. We grant you a limited, non-exclusive, non-transferable right to use the Service in accordance with these Terms.',
      'You retain ownership of your own content. You grant us a limited license to host, process, and transmit your content solely to operate and provide the Service to you.',
    ],
  },
  {
    heading: '10. Account Termination',
    body: [
      'You may stop using the Service and delete your account at any time. We may suspend or terminate your access if you violate these Terms, misuse the Service, or where required by law.',
      'Upon termination, your right to use the Service ends. Certain provisions — such as intellectual property, disclaimers, and limitation of liability — survive termination.',
    ],
  },
  {
    heading: '11. Disclaimers',
    body: [
      'The Service is provided "as is" and "as available" without warranties of any kind, whether express or implied, including fitness for a particular purpose and non-infringement. We do not warrant that the Service will be uninterrupted, error-free, or that AI output will meet your requirements.',
    ],
  },
  {
    heading: '12. Limitation of Liability',
    body: [
      'To the maximum extent permitted by law, AutoSocial AI and its team will not be liable for any indirect, incidental, special, consequential, or punitive damages, or for any loss of profits, data, goodwill, or reputation, arising from your use of the Service.',
      'Our total liability for any claim relating to the Service will not exceed the amount you paid us in the twelve months before the event giving rise to the claim.',
    ],
  },
  {
    heading: '13. Changes to These Terms',
    body: [
      'We may update these Terms from time to time. If we make material changes, we will notify you through the app or by email. Continued use of the Service after changes take effect constitutes acceptance of the revised Terms.',
    ],
  },
  {
    heading: '14. Contact',
    body: [`Questions about these Terms? Contact us at ${SITE.supportEmail}.`],
  },
]

export default function Terms() {
  return (
    <>
      <Seo
        title="Terms of Service"
        description="The terms governing your use of AutoSocial AI, including acceptable use, connected accounts, AI-generated content, and account terms."
      />
      <LegalPage title="Terms of Service" updated="July 8, 2026" sections={SECTIONS} />
    </>
  )
}
