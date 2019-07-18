
[![Build Status](https://travis-ci.com/wendykan/techparent.svg?token=vJ7kyxFoYH3y9JiG75HP&branch=master)](https://travis-ci.org/klugjo/hexo-autolinker)






commands for hugo

To run locally
> hugo server -D


To deploy to Firebase
> hugo && firebase deploy



To set up CI on Travis
following this guide: https://medium.com/@bartwijnants/continuous-deployment-to-firebase-hosting-using-travis-ci-e7d9c798ead4

> firebase login:ci

``` 
docker run -it --rm ruby:latest bash
gem install travis
travis encrypt "1/firebase_CI_token" -r githubusername/reponame
```

then add that encrypted token to `.travis.yml`

```
language: node_js
node_js:
  - "node"
script:
  -
deploy:
  provider: firebase
  token:
    secure: "encrypted_firebase_CI_token"
```