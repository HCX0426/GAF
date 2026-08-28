/**
 * OAuth callback handle page
 * from URL hash in extract access/refresh Token, storage after navigate to Dashboard.
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spin, App } from 'antd';
import { setAccessToken, setRefreshToken } from '@/utils/tokenStore';
import { useTranslation } from '@/i18n';

/** OAuth callback handle component */
export function OAuthCallbackPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const t = useTranslation();

  useEffect(() => {
    handleCallback();
  }, []);

  /** handle OAuth callback, parse hash in Token and navigate */
  const handleCallback = () => {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const access = params.get('access');
    const refresh = params.get('refresh');

    if (access && refresh) {
      setAccessToken(access);
      setRefreshToken(refresh);
      message.success(t('oauthCallback.msg_success'));
      navigate('/dashboard', { replace: true });
    } else {
      message.error(t('oauthCallback.msg_failed'));
      navigate('/login', { replace: true });
    }
  };

  return (
    <div className="gaf-flex-center gaf-justify-center" style={{ minHeight: '100vh' }}>
      <Spin size="large" description={t('oauthCallback.loading')} />
    </div>
  );
}

export default OAuthCallbackPage;
