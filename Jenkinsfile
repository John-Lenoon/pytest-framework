pipeline {
    agent { label 'linux' }

    options {
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        booleanParam(name: 'RUN_E2E', defaultValue: false,
            description: 'Run the real mall API suite after framework tests')
        string(name: 'PYTEST_MARKER', defaultValue: 'smoke',
            description: 'Pytest marker expression for real API tests')
        choice(name: 'XDIST_WORKERS', choices: ['auto', '2', '1'],
            description: 'Parallel workers for real API tests')
    }

    environment {
        PYTHONUNBUFFERED = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
            }
        }

        stage('Install') {
            steps {
                sh '''
                    python3 -m venv .venv
                    .venv/bin/python -m pip install --upgrade pip
                    .venv/bin/python -m pip install -r requirements.txt
                '''
            }
        }

        stage('Framework tests') {
            steps {
                sh 'PATH="$WORKSPACE/.venv/bin:$PATH" bash scripts/ci_test.sh framework'
            }
        }

        stage('Mall E2E') {
            when { expression { params.RUN_E2E } }
            environment {
                PYTEST_BASE_URL = credentials('mall-api-base-url')
                PYTEST_MEMBER_USERNAME = credentials('mall-member-username')
                PYTEST_MEMBER_PASSWORD = credentials('mall-member-password')
                PYTEST_ADMIN_USERNAME = credentials('mall-admin-username')
                PYTEST_ADMIN_PASSWORD = credentials('mall-admin-password')
            }
            steps {
                sh 'PATH="$WORKSPACE/.venv/bin:$PATH" bash scripts/ci_test.sh e2e "$PYTEST_MARKER" "$XDIST_WORKERS"'
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'junit-*.xml'
            allure includeProperties: false, results: [[path: 'allure-results']]
            archiveArtifacts allowEmptyArchive: true,
                artifacts: 'allure-results/**,reports/*.html,junit-*.xml'
            script {
                if (fileExists('.venv/bin/python') && env.DINGTALK_WEBHOOK?.trim()) {
                    withEnv(["TEST_STATUS=${currentBuild.currentResult}"]) {
                        sh '''
                            .venv/bin/python scripts/notify_dingtalk.py \
                              --status "$TEST_STATUS" \
                              --suite "Jenkins pytest-framework" \
                              --run-url "$BUILD_URL"
                        '''
                    }
                }
            }
        }
    }
}
